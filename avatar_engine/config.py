"""
Avatar Engine configuration handling.

Provides YAML configuration loading and validation.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .types import ProviderType


@dataclass
class AvatarConfig:
    """
    Avatar Engine configuration.

    Can be loaded from a YAML file or created programmatically.
    """
    provider: ProviderType = ProviderType.GEMINI
    model: Optional[str] = None
    working_dir: str = ""
    timeout: int = 120
    system_prompt: str = ""
    provider_kwargs: Dict[str, Any] = field(default_factory=dict)

    # Provider-specific configs
    gemini_config: Dict[str, Any] = field(default_factory=dict)
    claude_config: Dict[str, Any] = field(default_factory=dict)
    codex_config: Dict[str, Any] = field(default_factory=dict)

    # Safety
    safety_instructions: bool = True

    # Engine settings
    max_history: int = 100
    auto_restart: bool = True
    max_restarts: int = 3
    health_check_interval: int = 30  # seconds, 0 = disabled

    # Logging
    log_level: str = "INFO"
    log_file: str = ""
    log_format: str = "%(asctime)s %(name)s %(levelname)s %(message)s"
    log_max_bytes: int = 10485760  # 10MB
    log_backup_count: int = 3

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 60  # requests per minute
    rate_limit_burst: int = 10

    # Metrics
    metrics_enabled: bool = False
    metrics_type: str = "simple"  # prometheus, opentelemetry, simple
    metrics_port: int = 9090

    @classmethod
    def load(cls, path: str) -> "AvatarConfig":
        """
        Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            AvatarConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid YAML
        """
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AvatarConfig":
        """
        Create configuration from a dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            AvatarConfig instance
        """
        # Determine provider
        provider_str = data.get("provider", "gemini").lower()
        provider = ProviderType(provider_str)

        # Get provider-specific config
        gemini_cfg = data.get("gemini", {})
        claude_cfg = data.get("claude", {})
        codex_cfg = data.get("codex", {})

        # Get active provider config
        provider_configs = {
            ProviderType.GEMINI: gemini_cfg,
            ProviderType.CLAUDE: claude_cfg,
            ProviderType.CODEX: codex_cfg,
        }
        active_cfg = provider_configs.get(provider, gemini_cfg)

        # Engine settings
        engine_cfg = data.get("engine", data.get("avatar", {}))
        logging_cfg = data.get("logging", {})
        rate_limit_cfg = data.get("rate_limit", {})
        metrics_cfg = data.get("metrics", {})

        # Build provider kwargs (everything except common fields)
        provider_kwargs = {k: v for k, v in active_cfg.items()
                          if k not in ("timeout", "system_prompt", "model")}

        return cls(
            provider=provider,
            model=active_cfg.get("model"),
            working_dir=engine_cfg.get("working_dir", ""),
            timeout=active_cfg.get("timeout", 120),
            system_prompt=active_cfg.get("system_prompt", ""),
            provider_kwargs=provider_kwargs,
            gemini_config=gemini_cfg,
            claude_config=claude_cfg,
            codex_config=codex_cfg,
            safety_instructions=engine_cfg.get("safety_instructions", True),
            max_history=engine_cfg.get("max_history", 100),
            auto_restart=engine_cfg.get("auto_restart", True),
            max_restarts=engine_cfg.get("max_restarts", 3),
            health_check_interval=engine_cfg.get("health_check_interval", 30),
            log_level=logging_cfg.get("level", "INFO"),
            log_file=logging_cfg.get("file", ""),
            log_format=logging_cfg.get("format", "%(asctime)s %(name)s %(levelname)s %(message)s"),
            log_max_bytes=logging_cfg.get("max_bytes", 10485760),
            log_backup_count=logging_cfg.get("backup_count", 3),
            rate_limit_enabled=rate_limit_cfg.get("enabled", True),
            rate_limit_rpm=rate_limit_cfg.get("requests_per_minute", 60),
            rate_limit_burst=rate_limit_cfg.get("burst", 10),
            metrics_enabled=metrics_cfg.get("enabled", False),
            metrics_type=metrics_cfg.get("type", "simple"),
            metrics_port=metrics_cfg.get("port", 9090),
        )

    def get_provider_config(self) -> Dict[str, Any]:
        """
        Get the configuration for the active provider.

        Returns:
            Provider-specific configuration dictionary
        """
        if self.provider == ProviderType.GEMINI:
            return self.gemini_config
        elif self.provider == ProviderType.CODEX:
            return self.codex_config
        return self.claude_config

    def get_working_dir(self) -> str:
        """
        Get the resolved working directory.

        Returns:
            Absolute path to working directory
        """
        if self.working_dir:
            return str(Path(self.working_dir).expanduser().resolve())
        return os.getcwd()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.

        Returns:
            Configuration as dictionary
        """
        return {
            "provider": self.provider.value,
            "gemini": self.gemini_config,
            "claude": self.claude_config,
            "codex": self.codex_config,
            "engine": {
                "working_dir": self.working_dir,
                "safety_instructions": self.safety_instructions,
                "max_history": self.max_history,
                "auto_restart": self.auto_restart,
                "max_restarts": self.max_restarts,
                "health_check_interval": self.health_check_interval,
            },
            "logging": {
                "level": self.log_level,
                "file": self.log_file,
                "format": self.log_format,
                "max_bytes": self.log_max_bytes,
                "backup_count": self.log_backup_count,
            },
            "rate_limit": {
                "enabled": self.rate_limit_enabled,
                "requests_per_minute": self.rate_limit_rpm,
                "burst": self.rate_limit_burst,
            },
            "metrics": {
                "enabled": self.metrics_enabled,
                "type": self.metrics_type,
                "port": self.metrics_port,
            },
        }

    def save(self, path: str) -> None:
        """
        Save configuration to a YAML file.

        Args:
            path: Path to save the configuration file
        """
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, allow_unicode=True)
