"""Create an independent report without changing coursework storage."""

import os
import tempfile
import uuid
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from src.config import PROJECT_ROOT
from src.exceptions import ReportError
from src.reporting.renderer import render_report
from src.snapshots import FlightSnapshot


class SnapshotSource(Protocol):
    """The report needs an observation snapshot, not storage."""

    def get_snapshot(self, country: str) -> FlightSnapshot:
        """Fetch the country and its current aircraft positions."""
        ...


class ReportService:
    """Fetch and atomically save a self-contained HTML report."""

    def __init__(
        self,
        source: SnapshotSource,
        output_dir: Path | str | None = None,
    ) -> None:
        self.__source = source
        self.__output_dir = (
            PROJECT_ROOT / "reports"
            if output_dir is None
            else Path(output_dir).resolve()
        )

    def create(self, country: str) -> Path:
        """Return a saved report; never write the main aircraft JSON."""
        if not isinstance(country, str):
            raise TypeError("Название страны должно быть строкой.")
        if not country.strip():
            raise ValueError("Название страны не должно быть пустым.")
        snapshot = self.__source.get_snapshot(country.strip())
        temporary_path: Path | None = None
        try:
            content = render_report(snapshot)
            self.__output_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            target = self.__output_dir / (
                f"airspace-{stamp}-{uuid.uuid4().hex[:8]}.html"
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.__output_dir,
                prefix=".airspace-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, target)
            return target
        except (
            OSError,
            UnicodeError,
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ReportError(f"Не удалось создать HTML-отчёт: {exc}") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


def open_report(
    path: Path, opener: Callable[[str], bool] | None = None
) -> bool:
    """Opening a browser is optional: the saved file remains usable."""
    try:
        return bool(
            (webbrowser.open if opener is None else opener)(
                path.resolve().as_uri()
            )
        )
    except (OSError, webbrowser.Error):
        return False
