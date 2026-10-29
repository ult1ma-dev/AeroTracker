"""Проверка запуска программы отдельным процессом без HTTP."""

import os
import subprocess
import sys
from pathlib import Path


def test_main_starts_outside_project_directory(tmp_path):
    project = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(project / "main.py")],
        input="0\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "PYTHONUTF8": "1",
            "AEROPLANES_DATA_FILE": str(tmp_path / "missing.json"),
        },
        cwd=tmp_path,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert "До свидания!" in result.stdout
    assert result.stderr == ""


def test_import_main_has_no_side_effects(capsys):
    import main

    assert callable(main.main)
    assert capsys.readouterr().out == ""
