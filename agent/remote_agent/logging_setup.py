"""
Настройка логирования для агента.

Вся информация, которая ранее выводилась через print(), теперь пишется:
  - в файл с ротацией по размеру (RotatingFileHandler),
  - одновременно в консоль (StreamHandler).

Параметры (log_file, max_bytes, backup_count) берутся из config.py,
так что для изменения поведения достаточно отредактировать только config.py.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    log_file: str | Path,
    max_bytes: int,
    backup_count: int,
    level: int = logging.INFO,
) -> None:
    """
    Инициализирует root-логгер один раз для всего процесса.

    Параметры
    ----------
    log_file     : путь к лог-файлу (будет создан автоматически).
    max_bytes    : максимальный размер файла перед ротацией.
    backup_count : сколько архивных копий хранить.
    level        : минимальный уровень записи (по умолчанию INFO).
    """
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- ротирующий файловый обработчик ---
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # --- консольный обработчик (дублирует вывод, как было с print) ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Защита от повторного вызова setup_logging (актуально при тестах)
    if root_logger.handlers:
        root_logger.handlers.clear()

    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)