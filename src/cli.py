"""Консольный ввод, меню и представление самолётов."""

from collections.abc import Callable, Sequence
from pathlib import Path

from src.api import AeroplanesAPI
from src.config import Settings
from src.exceptions import AeroplanesError, RateLimitError
from src.models import Aeroplane
from src.reporting.service import ReportService, open_report
from src.services import AeroplanesService, validate_altitude_range
from src.storage import JSONSaver

Input = Callable[[str], str]
Output = Callable[[str], None]

MENU = """
1 — Запросить самолёты выбранной страны
2 — Показать текущий список
3 — Топ N по высоте
4 — Фильтр по стране регистрации
5 — Фильтр по диапазону высот
6 — Повторно загрузить JSON
7 — Удалить самолёт по ICAO24
8 — [Дополнительно] Карта и HTML-отчёт
0 — Выход"""


def print_aeroplanes(
    aeroplanes: Sequence[Aeroplane], output: Output = print
) -> None:
    """Печатает все выбранные записи с единицами измерения."""
    if not aeroplanes:
        output("Подходящих самолётов нет.")
        return
    for index, plane in enumerate(aeroplanes, start=1):
        altitude = (
            "нет данных" if plane.altitude is None else f"{plane.altitude:g} м"
        )
        velocity = (
            "нет данных"
            if plane.velocity is None
            else f"{plane.velocity:g} м/с"
        )
        status = "на земле" if plane.on_ground else "в воздухе"
        output(
            f"{index}. {plane.callsign or 'Без позывного'} "
            f"[{plane.icao24}] | {plane.origin_country} | "
            f"высота: {altitude} | скорость: {velocity} | {status}"
        )


def _read_nonempty(prompt: str, read: Input, output: Output) -> str:
    while True:
        value = read(prompt).strip()
        if value:
            return value
        output("Значение не должно быть пустым.")


def _read_top_n(read: Input, output: Output) -> int:
    while True:
        raw = read("Количество самолётов N: ").strip()
        try:
            number = int(raw)
            if number > 0:
                return number
        except ValueError:
            pass
        output("Введите целое положительное число.")


def _read_countries(read: Input, output: Output) -> list[str]:
    while True:
        raw = read("Страны регистрации через запятую: ")
        countries = [country.strip() for country in raw.split(",")]
        if countries and all(countries):
            return countries
        output("Введите полные названия стран, разделяя их запятыми.")


def _read_altitudes(read: Input, output: Output) -> tuple[float, float]:
    while True:
        try:
            minimum = float(read("Минимальная высота, м: "))
            maximum = float(read("Максимальная высота, м: "))
            validate_altitude_range(minimum, maximum)
            return minimum, maximum
        except ValueError as exc:
            output(f"Некорректный диапазон: {exc}")


def _show_error(exc: AeroplanesError, output: Output) -> None:
    output(f"Ошибка: {exc}")
    if isinstance(exc, RateLimitError) and exc.retry_after is not None:
        output(f"Повторите запрос через {exc.retry_after:g} с.")


def _run_menu(
    service: AeroplanesService,
    read: Input,
    output: Output,
    create_report: Callable[[str], Path],
    open_browser: Callable[[str], bool] | None,
) -> None:
    output("Самолёты: данные OpenSky Network, границы © OpenStreetMap.")
    output("Границы прямоугольные и могут включать соседние территории.")
    output("Данные из файла являются сохранённым снимком, а не онлайн-лентой.")
    try:
        saved = service.load_saved()
        output(f"Из JSON загружено самолётов: {len(saved)}.")
    except AeroplanesError as exc:
        _show_error(exc, output)

    while True:
        output(MENU)
        action = read("Выберите действие: ").strip()
        try:
            if action == "0":
                output("До свидания!")
                return
            if action == "1":
                country = _read_nonempty("Название страны: ", read, output)
                loaded = service.fetch_country(country)
                output(f"Получено и сохранено самолётов: {len(loaded)}.")
            elif action == "2":
                print_aeroplanes(service.aeroplanes, output)
            elif action == "3":
                number = _read_top_n(read, output)
                unknown = sum(
                    plane.altitude is None for plane in service.aeroplanes
                )
                if unknown:
                    output(f"Без известной высоты исключено: {unknown}.")
                print_aeroplanes(service.top(number), output)
            elif action == "4":
                countries = _read_countries(read, output)
                print_aeroplanes(service.by_origin(countries), output)
            elif action == "5":
                minimum, maximum = _read_altitudes(read, output)
                print_aeroplanes(service.by_altitude(minimum, maximum), output)
            elif action == "6":
                loaded = service.load_saved()
                output(f"Из JSON загружено самолётов: {len(loaded)}.")
            elif action == "7":
                icao24 = _read_nonempty("ICAO24 для удаления: ", read, output)
                deleted = service.delete(icao24)
                output("Запись удалена." if deleted else "Самолёт не найден.")
            elif action == "8":
                country = _read_nonempty(
                    "Страна для карты и отчёта: ", read, output
                )
                output("Создаю дополнительную карту и HTML-отчёт…")
                path = create_report(country)
                output(f"Отчёт сохранён: {path}")
                if not open_report(path, open_browser):
                    output(
                        "Браузер не открылся автоматически. "
                        "Откройте сохранённый HTML-файл вручную."
                    )
            else:
                output("Неизвестное действие. Выберите пункт меню.")
        except AeroplanesError as exc:
            _show_error(exc, output)
        except (TypeError, ValueError) as exc:
            output(f"Ошибка ввода: {exc}")


def user_interaction(
    service: AeroplanesService | None = None,
    *,
    report_service: ReportService | None = None,
    read: Input | None = None,
    output: Output = print,
    open_browser: Callable[[str], bool] | None = None,
) -> None:
    """Запускает меню; зависимости можно подменить в тестах."""
    api: AeroplanesAPI | None = None

    def create_report(country: str) -> Path:
        nonlocal api, report_service
        if report_service is None:
            if api is None:
                settings = Settings.from_env()
                api = AeroplanesAPI(
                    nominatim_url=settings.nominatim_url,
                    opensky_url=settings.opensky_url,
                    user_agent=settings.user_agent,
                    timeout=settings.timeout,
                )
            report_service = ReportService(api)
        return report_service.create(country)

    try:
        if service is None:
            settings = Settings.from_env()
            api = AeroplanesAPI(
                nominatim_url=settings.nominatim_url,
                opensky_url=settings.opensky_url,
                user_agent=settings.user_agent,
                timeout=settings.timeout,
            )
            service = AeroplanesService(api, JSONSaver(settings.data_file))
        _run_menu(
            service,
            input if read is None else read,
            output,
            create_report,
            open_browser,
        )
    except (EOFError, KeyboardInterrupt):
        output("\nРабота завершена.")
    except (TypeError, ValueError) as exc:
        output(f"Ошибка настройки: {exc}")
    finally:
        if api is not None:
            api.close()
