#!/usr/bin/env python3

from dataclasses import dataclass
import datetime
import sqlite3
from typing import Dict, Tuple
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme

# Кастомизируем тему оформления
custom_theme = Theme({
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "info": "bold blue",
    "header": "bold magenta",
    "menu": "bold cyan",
    "prompt": "bold",
})
console = Console(theme=custom_theme)

@dataclass
class LogRecord:
    mileage: int
    service_date: datetime.date
    type_: str
    service_description: str

def generate_null_record() -> LogRecord:
    return LogRecord(0, datetime.date.today(), '', '')

SERVICE_TYPE = {
    0: 'плановое ТО',
    1: 'внеплановый ремонт',
}

PLANNED_WORK_WITH_PERIOD = {
    0: ("Замена масла в двигателе", 15000),
    1: ("Замена масляного фильтра", 15000),
    2: ("Замена тормозных дисков", 100000),
    3: ("Замена топливного фильтра", 80000),
    4: ("Замена воздушного фильтра для двигателя", 40000),
    5: ("Замена воздушного фильтра для салона", 20000),
    6: ("Замена свечей зажигания", 100000),
    7: ("Замена тормозной жидкости", 40000),
    8: ("Замена масла в раздаточной коробке", 100000),
    9: ("Замена масла в механизме заднего дифференциала", 100000),  
    10: ('Замена охлаждающей жидкости двигателя', 80000),
    11: ("Замена масла в АКПП", 100000), 
}

# SQL-запросы
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, 
    mileage INT NOT NULL, 
    date VARCHAR(40) NOT NULL, 
    type VARCHAR(18) NOT NULL, 
    description VARCHAR(80) NOT NULL
);
"""

CREATE_RECORD_SQL = """
INSERT INTO logs (mileage, date, type, description) 
VALUES (?, ?, ?, ?)
"""

GET_LAST_SERVICE_SQL = """
SELECT mileage 
FROM logs 
WHERE description = ? 
ORDER BY mileage DESC 
LIMIT 1
"""

GET_ALL_RECORDS_SQL = "SELECT * FROM logs"

class CarLogger:
    def __init__(self, db_path: str = 'car_logger.db'):
        self._db_path = db_path
        self._main_table_name = 'logs'
        self._initialize_database()
        
    def _get_connection(self) -> sqlite3.Connection:
        """Возвращает новое соединение с базой данных"""
        return sqlite3.connect(self._db_path)
    
    def _initialize_database(self) -> None:
        """Создает таблицу, если она не существует"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(CREATE_TABLE_SQL)
            conn.commit()
    
    def check_necessary_service(self, current_mileage: int) -> Dict[str, Tuple[int, int]]:
        """
        Проверяет необходимость сервиса для всех работ.
        Возвращает словарь работ, требующих обслуживания.
        """
        service_required = {}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("[info]Проверка состояния автомобиля...", total=len(PLANNED_WORK_WITH_PERIOD))
                
                for work_id, (work_desc, period) in PLANNED_WORK_WITH_PERIOD.items():
                    progress.update(task, advance=1, description=f"Проверка: {work_desc[:20]}...")
                    cursor.execute(GET_LAST_SERVICE_SQL, (work_desc,))
                    result = cursor.fetchone()
                    last_mileage = result[0] if result else 0
                    next_service = last_mileage + period
                    admission = int(period * 0.1)  # 10% допуск
                    
                    if current_mileage >= next_service - admission:
                        service_required[work_desc] = (last_mileage, next_service)
        
        return service_required

    def create_record(self, record: LogRecord) -> int:
        """Создает новую запись в базе данных, возвращает ID записи"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                CREATE_RECORD_SQL,
                (
                    record.mileage, 
                    record.service_date.isoformat(), 
                    record.type_, 
                    record.service_description
                )
            )
            conn.commit()
            return cursor.lastrowid
        
    def display_service_status(self, current_mileage: int) -> None:
            """Отображает статус сервиса в виде наглядной панели"""
            try:
                service_required = self.check_necessary_service(current_mileage)
            except sqlite3.OperationalError as e:
                console.print(f"[error]Ошибка при доступе к базе данныnх: {e}[/error]")
                return
            
            if not service_required:
                console.print(Panel(
                    "✅ [success]Все системы в норме, сервис не требуется![/success]",
                    title="Статус автомобиля",
                    title_align="center",
                    style="success",
                    padding=(1, 4),
                    width=80
                ), justify="center")
                return
            
            table = Table(
                title="\nТребуется обслуживание",
                title_style="warning",
                show_header=True,
                header_style="warning",
                expand=True
            )
            table.add_column("Работа", style="info")
            table.add_column("Последнее ТО", justify="right")
            table.add_column("Следующее ТО", justify="right")
            table.add_column("Текущий пробег", justify="right")
            table.add_column("Статус", justify="center")
            
            for work_desc, (last_mileage, next_service) in service_required.items():
                status = "[warning]ТРЕБУЕТСЯ![/warning]" if current_mileage >= next_service else "[info]Скоро потребуется[/info]"
                table.add_row(
                    work_desc,
                    f"{last_mileage:,}".replace(",", " "),
                    f"{next_service:,}".replace(",", " "),
                    f"{current_mileage:,}".replace(",", " "),
                    status
                )
            
            console.print(table, justify="center")

    def show_service_history(self) -> None:
        """Отображает историю обслуживания в виде красивой таблицы"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(GET_ALL_RECORDS_SQL)
            rows = cursor.fetchall()
            
            if not rows:
                console.print("[warning]История обслуживания пуста[/warning]", justify="center")
                return
                
            table = Table(
                title="\nИстория обслуживания автомобиля",
                title_style="header",
                show_header=True,
                header_style="menu",
                show_lines=True,
                expand=True
            )
            
            table.add_column("ID", style="info", width=5, justify="center")
            table.add_column("Пробег (км)", justify="right")
            table.add_column("Дата", justify="center")
            table.add_column("Тип обслуживания", min_width=20)
            table.add_column("Описание работ", min_width=35)
            
            for row in rows:
                # Форматируем дату
                try:
                    # Пытаемся преобразовать строку в дату
                    service_date = datetime.date.fromisoformat(row[2])
                except ValueError:
                    # Если не получается, оставляем как есть
                    formatted_date = row[2]
                else:
                    formatted_date = service_date.strftime("%d.%m.%Y")
                # Определяем стиль в зависимости от типа обслуживания
                service_style = "success" if "плановое" in row[3] else "warning"
                
                table.add_row(
                    str(row[0]),
                    f"{row[1]:,}".replace(",", " "),
                    formatted_date,
                    f"[{service_style}]{row[3]}[/]",
                    row[4]
                )
            
            console.print(table, justify="center")

def display_planned_services(show_title: bool = True) -> None:
    """Отображает плановые сервисные работы с улучшенным оформлением"""
    if show_title:
        console.rule("[header]Процедуры планового ТО[/header]", align="center")
    
    table = Table(
        title="\nПериодичность планового технического обслуживания" if show_title else None,
        title_style="header",
        show_header=True,
        header_style="menu",
        width=70,
        show_lines=True,
    )
    table.add_column("Код", style="info", justify="center", width=8)
    table.add_column("Процедура", min_width=45)
    table.add_column("Интервал (км)", justify="right", width=15)
    
    for code, (work, interval) in PLANNED_WORK_WITH_PERIOD.items():
        table.add_row(
            f"[bold]{code}[/bold]",
            work,
            f"[bold]{interval // 1000} тыс.[/bold]"
        )
    
    # Добавляем поясняющую панель
    if show_title:
        console.print(
            Panel(
                "В этом разделе представлен полный перечень регулярных\n"
                "технических процедур с рекомендованными интервалами\n"
                "пробега для вашего автомобиля",
                title="ℹ️ Информация",
                title_align="left",
                style="info",
                width=70,
                padding=(1, 2)
            ),
            justify="center"
        )
        console.print()
    
    console.print(table, justify="center")
    
    if show_title:
        console.print(
            Panel(
                "[bold]Важно:[/bold] Фактические интервалы могут отличаться в зависимости "
                "от условий эксплуатации, рекомендаций производителя и технического состояния автомобиля",
                style="warning",
                width=70,
                padding=(1, 2)
            ),
            justify="center"
        )


def display_main_menu() -> None:
    """Отображает главное меню"""
    console.print(Panel(
        "[bold]🚗 Автомобильный сервисный журнал[/bold]",
        subtitle="Управляйте историей обслуживания вашего автомобиля",
        style="menu",
        padding=(1, 4),
        width=80
    ), justify="center")
    
    menu = Table.grid(padding=(0, 3))
    menu.add_column(style="menu")
    menu.add_row("1. Проверить состояние автомобиля")
    menu.add_row("2. Добавить запись об обслуживании")
    menu.add_row("3. Просмотреть историю обслуживания")
    menu.add_row("4. Процедуры планового ТО")  # Новый пункт меню
    menu.add_row("5. Выход")  # Выход теперь пункт 5
    
    console.print(menu, justify="center")


def display_service_types() -> None:
    """Отображает типы сервиса"""
    table = Table(
        title="Типы обслуживания",
        title_style="menu",
        show_header=False,
        padding=(0, 2),
        width=50
    )
    table.add_column("Код", style="info", justify="center")
    table.add_column("Тип обслуживания")
    
    for code, service_type in SERVICE_TYPE.items():
        table.add_row(str(code), service_type)
    
    console.print(table, justify="center")


def display_planned_services(show_title: bool = True) -> None:
    """Отображает плановые сервисные работы с улучшенным оформлением"""
    if show_title:
        console.rule("[header]Процедуры планового ТО[/header]", align="center")
    
    table = Table(
        title="\nПериодичность планового технического обслуживания" if show_title else None,
        title_style="header",
        show_header=True,
        header_style="menu",
        width=70,
        box=None if not show_title else None,
        show_lines=True,
    )
    table.add_column("Код", style="info", justify="center", width=8)
    table.add_column("Процедура", min_width=45)
    table.add_column("Интервал (км)", justify="right", width=15)
    
    for code, (work, interval) in PLANNED_WORK_WITH_PERIOD.items():
        table.add_row(
            f"[bold]{code}[/bold]",
            work,
            f"[bold]{interval // 1000} тыс.[/bold]"
        )
    
    # Добавляем поясняющую панель
    if show_title:
        console.print(
            Panel(
                "В этом разделе представлен полный перечень регулярных\n"
                "технических процедур с рекомендованными интервалами\n"
                "пробега для вашего автомобиля",
                title="ℹ️ Информация",
                title_align="left",
                style="info",
                width=70,
                padding=(1, 2)),
            justify="center"
        )
        console.print()
    
    console.print(table, justify="center")
    
    if show_title:
        console.print(
            Panel(
                "[bold]Важно:[/bold] Фактические интервалы могут отличаться в зависимости "
                "от условий эксплуатации, рекомендаций производителя и технического состояния автомобиля",
                style="warning",
                width=70,
                padding=(1, 2)),
            justify="center"
        )


def main():
    car_logger = CarLogger()
    
    # Приветственное сообщение
    console.print(Panel(
        "[bold]🚘 Добро пожаловать в систему учета сервисных работ![/bold]",
        subtitle="Ваш надежный помощник в обслуживании автомобиля",
        style="header",
        padding=(1, 4),
        width=80,
    ), justify="center")
    
    while True:
        display_main_menu()
        choice = IntPrompt.ask(
            "\n[prompt]Выберите действие[/prompt]", 
            choices=["1", "2", "3", "4", "5"],  # Добавлен выбор 4 и 5
            show_choices=False
        )
        
        if choice == 1:  # Проверка состояния
            console.rule("[header]Проверка состояния автомобиля[/header]", align="center")
            mileage = IntPrompt.ask("[prompt]Введите текущий пробег автомобиля (км)[/prompt]")
            
            with console.status("[info]Анализ состояния автомобиля...[/info]", spinner="dots"):
                car_logger.display_service_status(mileage)
            
        elif choice == 2:  # Добавление записи
            console.rule("[header]Добавление записи об обслуживании[/header]", align="center")
            new_record = generate_null_record()
            
            new_record.mileage = IntPrompt.ask("[prompt]Введите пробег автомобиля (км)[/prompt]")
            new_record.service_date = datetime.date.today()
            
            display_service_types()
            service_type = IntPrompt.ask(
                "[prompt]Выберите тип обслуживания[/prompt]", 
                choices=[str(k) for k in SERVICE_TYPE.keys()]
            )
            new_record.type_ = SERVICE_TYPE[service_type]
            
            if service_type == 0:  # Плановое ТО
                display_planned_services(show_title=False)  # Упрощенное отображение
                work_type = IntPrompt.ask(
                    "[prompt]Выберите выполненную работу[/prompt]", 
                    choices=[str(k) for k in PLANNED_WORK_WITH_PERIOD.keys()]
                )
                new_record.service_description = PLANNED_WORK_WITH_PERIOD[int(work_type)][0]
            else:  # Внеплановый ремонт
                new_record.service_description = Prompt.ask("[prompt]Опишите выполненную работу[/prompt]")
            
            record_id = car_logger.create_record(new_record)
            console.print(f"\n[success]✅ Запись #{record_id} успешно добавлена в журнал![/success]")
            
        elif choice == 3:  # Просмотр истории
            console.rule("[header]История обслуживания[/header]", align="center")
            car_logger.show_service_history()
            
        elif choice == 4:  # Новый пункт - Процедуры планового ТО
            display_planned_services(show_title=True)  # Полноценное отображение
            
        elif choice == 5:  # Выход (теперь пункт 5)
            console.print("\n[info]🚗 Благодарим за использование сервиса! Хорошей дороги![/info]")
            break
        
        # Продолжить или выйти
        if choice != 5:  # Обновлено на 5
            if not Confirm.ask("\n[prompt]Желаете выполнить ещё одну операцию?[/prompt]", default=True):
                console.print("\n[info]🚗 Благодарим за использование сервиса! Хорошей дороги![/info]")
                break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[info]🚗 Работа программы завершена. Хорошей дороги![/info]")
