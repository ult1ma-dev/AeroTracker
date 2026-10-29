"""Ошибки приложения, пригодные для отображения в консоли."""


class AeroplanesError(Exception):
    """Базовая ошибка приложения."""


class APIError(AeroplanesError):
    """Ошибка обращения к внешнему сервису."""


class CountryNotFoundError(APIError):
    """Запрошенная страна не найдена."""


class APIResponseError(APIError):
    """Ответ сервиса не соответствует ожидаемому формату."""


class RateLimitError(APIError):
    """Внешний сервис ограничил частоту запросов."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class StorageError(AeroplanesError):
    """Ошибка чтения или записи хранилища."""


class ReportError(AeroplanesError):
    """Ошибка создания дополнительного HTML-отчёта."""
