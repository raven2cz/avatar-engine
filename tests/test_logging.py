"""Tests for avatar_engine.utils.logging module."""

import logging
import os
import tempfile
import pytest
from avatar_engine.config import AvatarConfig
from avatar_engine.utils.logging import setup_logging, setup_logging_from_dict, get_logger


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_with_defaults(self):
        """Should setup logging with sensible defaults."""
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) >= 1

    def test_setup_with_config(self):
        """Should setup logging from AvatarConfig."""
        config = AvatarConfig(log_level="DEBUG")
        setup_logging(config)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_setup_with_file(self):
        """Should create file handler when log_file is specified."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_file = f.name

        try:
            config = AvatarConfig(log_file=log_file)
            setup_logging(config)

            # Log something
            logger = logging.getLogger("test")
            logger.info("Test message")

            # Check file was written
            with open(log_file) as f:
                content = f.read()
            assert "Test message" in content
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)

    def test_setup_with_custom_format(self):
        """Should use custom log format."""
        config = AvatarConfig(log_format="[%(levelname)s] %(message)s")
        setup_logging(config)
        root = logging.getLogger()
        # Check that formatter was set
        assert root.handlers[0].formatter._fmt == "[%(levelname)s] %(message)s"


class TestSetupLoggingFromDict:
    """Tests for setup_logging_from_dict function."""

    def test_setup_from_dict(self):
        """Should setup logging from dictionary."""
        setup_logging_from_dict({"level": "WARNING"})
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_setup_from_dict_with_file(self):
        """Should create file handler from dict config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            log_file = f.name

        try:
            setup_logging_from_dict({
                "level": "INFO",
                "file": log_file,
                "format": "%(message)s",
            })

            # Log something
            logger = logging.getLogger("test_dict")
            logger.info("Dict test message")

            # Check file was written
            with open(log_file) as f:
                content = f.read()
            assert "Dict test message" in content
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger(self):
        """Should return a logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_get_logger_same_instance(self):
        """Should return same logger for same name."""
        logger1 = get_logger("same.name")
        logger2 = get_logger("same.name")
        assert logger1 is logger2


class TestLoggingConfigIntegration:
    """Integration tests for logging configuration."""

    def test_config_to_dict_includes_logging(self):
        """Config.to_dict should include all logging settings."""
        config = AvatarConfig(
            log_level="DEBUG",
            log_file="test.log",
            log_format="%(message)s",
            log_max_bytes=1000,
            log_backup_count=5,
        )
        d = config.to_dict()

        assert d["logging"]["level"] == "DEBUG"
        assert d["logging"]["file"] == "test.log"
        assert d["logging"]["format"] == "%(message)s"
        assert d["logging"]["max_bytes"] == 1000
        assert d["logging"]["backup_count"] == 5

    def test_config_from_dict_loads_logging(self):
        """Config.from_dict should load all logging settings."""
        config = AvatarConfig.from_dict({
            "logging": {
                "level": "WARNING",
                "file": "app.log",
                "format": "[%(name)s] %(message)s",
                "max_bytes": 5000,
                "backup_count": 2,
            }
        })

        assert config.log_level == "WARNING"
        assert config.log_file == "app.log"
        assert config.log_format == "[%(name)s] %(message)s"
        assert config.log_max_bytes == 5000
        assert config.log_backup_count == 2
