"""
Logging configuration utilities for Avatar Engine.

Provides configurable logging with file rotation support.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from ..config import AvatarConfig


def setup_logging(config: Optional[AvatarConfig] = None) -> None:
    """
    Configure logging based on AvatarConfig settings.

    Args:
        config: AvatarConfig instance. If None, uses sensible defaults.

    Features:
        - Configurable log level (DEBUG, INFO, WARNING, ERROR)
        - Optional file logging with rotation
        - Custom log format

    Example:
        config = AvatarConfig.load("config.yaml")
        setup_logging(config)
    """
    if config is None:
        # Default configuration
        level = logging.INFO
        log_format = "%(asctime)s %(name)s %(levelname)s %(message)s"
        log_file = None
        max_bytes = 10485760
        backup_count = 3
    else:
        level = getattr(logging, config.log_level.upper(), logging.INFO)
        log_format = config.log_format
        log_file = config.log_file or None
        max_bytes = config.log_max_bytes
        backup_count = config.log_backup_count

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation (if configured)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def setup_logging_from_dict(config_dict: dict) -> None:
    """
    Configure logging from a dictionary.

    Args:
        config_dict: Dictionary with logging configuration.
            - level: Log level (DEBUG, INFO, WARNING, ERROR)
            - file: Optional log file path
            - format: Log format string
            - max_bytes: Max file size before rotation
            - backup_count: Number of backup files to keep

    Example:
        setup_logging_from_dict({
            "level": "DEBUG",
            "file": "avatar.log",
            "format": "%(asctime)s - %(message)s",
            "max_bytes": 5242880,
            "backup_count": 5,
        })
    """
    level_str = config_dict.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    log_format = config_dict.get("format", "%(asctime)s %(name)s %(levelname)s %(message)s")
    log_file = config_dict.get("file")
    max_bytes = config_dict.get("max_bytes", 10485760)
    backup_count = config_dict.get("backup_count", 3)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(log_format)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation (if configured)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
