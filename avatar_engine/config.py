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

    # Engine settings
    max_history: int = 100
    auto_restart: bool = True
    max_restarts: int = 3

    # Logging
    log_level: str = "INFO"
    log_file: str = ""

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

        # Get active provider config
        active_cfg = gemini_cfg if provider == ProviderType.GEMINI else claude_cfg

        # Engine settings
        engine_cfg = data.get("engine", data.get("avatar", {}))
        logging_cfg = data.get("logging", {})

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
            max_history=engine_cfg.get("max_history", 100),
            auto_restart=engine_cfg.get("auto_restart", True),
            max_restarts=engine_cfg.get("max_restarts", 3),
            log_level=logging_cfg.get("level", "INFO"),
            log_file=logging_cfg.get("file", ""),
        )

    def get_provider_config(self) -> Dict[str, Any]:
        """
        Get the configuration for the active provider.

        Returns:
            Provider-specific configuration dictionary
        """
        if self.provider == ProviderType.GEMINI:
            return self.gemini_config
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
            "engine": {
                "working_dir": self.working_dir,
                "max_history": self.max_history,
                "auto_restart": self.auto_restart,
                "max_restarts": self.max_restarts,
            },
            "logging": {
                "level": self.log_level,
                "file": self.log_file,
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
