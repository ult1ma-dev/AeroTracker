"""Настройки приложения из переменных окружения."""

import math
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Настройки HTTP и пути к файлу с самолётами."""

    data_file: Path = PROJECT_ROOT / "data" / "aeroplanes.json"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    opensky_url: str = "https://opensky-network.org/api/states/all"
    user_agent: str = "SkyPro-Aeroplanes-Coursework/0.1.0"
    timeout: float = 10.0

    def __post_init__(self) -> None:
        for url in (self.nominatim_url, self.opensky_url):
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Адрес API должен быть HTTP(S)-адресом.")
        if not self.user_agent.strip():
            raise ValueError("User-Agent не должен быть пустым.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("HTTP_TIMEOUT должен быть положительным числом.")

    @classmethod
    def from_env(cls) -> "Settings":
        """Читает настройки; относительные пути — от корня проекта."""
        defaults = cls()
        raw_path = os.getenv("AEROPLANES_DATA_FILE", str(defaults.data_file))
        if not raw_path.strip():
            raise ValueError("AEROPLANES_DATA_FILE не должен быть пустым.")
        data_file = Path(raw_path).expanduser()
        if not data_file.is_absolute():
            data_file = PROJECT_ROOT / data_file
        try:
            timeout = float(os.getenv("HTTP_TIMEOUT", str(defaults.timeout)))
        except ValueError as exc:
            raise ValueError("HTTP_TIMEOUT должен быть числом.") from exc
        return cls(
            data_file=data_file,
            nominatim_url=os.getenv("NOMINATIM_URL", defaults.nominatim_url),
            opensky_url=os.getenv("OPENSKY_URL", defaults.opensky_url),
            user_agent=os.getenv("NOMINATIM_USER_AGENT", defaults.user_agent),
            timeout=timeout,
        )
