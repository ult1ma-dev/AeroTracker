"""Точка входа в консольное приложение."""

from src.cli import user_interaction


def main() -> None:
    """Запускает консольное приложение."""
    user_interaction()


if __name__ == "__main__":
    main()
