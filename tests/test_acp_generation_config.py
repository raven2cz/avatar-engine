"""
ACP Generation Config Propagation — Integration Tests.

Verify the end-to-end flow:
    frontend options → session_manager → engine → GeminiBridge → settings file

ACP mode uses two settings mechanisms:
  - ``customOverrides`` (array): generateContentConfig applied AFTER alias
    resolution — preserves the entire built-in alias chain.
  - ``customAliases``: model routing only (when non-default model).

model.name must NEVER appear in ACP mode settings.

These tests simulate the exact flow that happens when a user changes
model options in the web UI.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.engine import AvatarEngine


# =============================================================================
# Helper: simulate the web UI → session_manager → engine → bridge flow
# =============================================================================


def _simulate_switch(
    provider: str = "gemini",
    model: Optional[str] = "gemini-3-pro-preview",
    options: Optional[Dict[str, Any]] = None,
    working_dir: str = "/tmp",
) -> GeminiBridge:
    """Simulate the exact flow from EngineSessionManager.switch() to bridge.

    1. session_manager.switch() merges options into kwargs
    2. AvatarEngine.__init__(**kwargs) stores kwargs
    3. engine._create_bridge() extracts generation_config from kwargs
    4. GeminiBridge.__init__(generation_config=...) stores it
    5. bridge._setup_config_files() writes settings to sandbox

    Returns the bridge with settings already written (ready for inspection).
    """
    # Step 1-2: what session_manager + engine do
    kwargs: Dict[str, Any] = {}
    if options:
        kwargs.update(options)

    # Step 3: what engine._create_bridge() does for Gemini
    generation_config = kwargs.get("generation_config", {})

    # Step 4-5: create bridge and write config
    bridge = GeminiBridge(
        model=model or "",
        acp_enabled=True,
        generation_config=generation_config,
        working_dir=working_dir,
    )
    bridge._setup_config_files()
    return bridge


def _read_settings(bridge: GeminiBridge) -> Dict[str, Any]:
    """Read the settings file from bridge's sandbox."""
    assert bridge._gemini_settings_path is not None, (
        "Settings file should exist but _gemini_settings_path is None"
    )
    return json.loads(bridge._gemini_settings_path.read_text())


def _get_alias(settings: Dict[str, Any], alias_name: str = "gemini-3-pro-preview") -> Dict[str, Any]:
    """Extract a customAlias from settings dict (only for non-default models)."""
    return settings["modelConfigs"]["customAliases"][alias_name]


def _get_gen_cfg(settings: Dict[str, Any], model: str = "gemini-3-pro-preview") -> Dict[str, Any]:
    """Extract generateContentConfig from customOverrides matching a model."""
    overrides = settings["modelConfigs"]["customOverrides"]
    for override in overrides:
        if override["match"]["model"] == model:
            return override["modelConfig"]["generateContentConfig"]
    raise KeyError(f"No customOverride matching model={model}")


# =============================================================================
# Test: Thinking Level propagation (the most common use case)
# =============================================================================


class TestThinkingLevelPropagation:
    """Verify thinking_level flows from UI options to settings file."""

    def test_thinking_level_medium(self, tmp_path):
        """User selects 'Medium' in thinking level dropdown."""
        # Frontend buildOptionsDict produces this nested structure:
        options = {"generation_config": {"thinking_level": "medium"}}

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "MEDIUM"
        # Default model → no customAliases needed (only customOverrides)
        assert "customAliases" not in settings.get("modelConfigs", {})
        assert "model" not in settings  # No model.name at top level
        bridge._sandbox.cleanup()

    def test_thinking_level_high(self, tmp_path):
        """User selects 'High' thinking level."""
        options = {"generation_config": {"thinking_level": "high"}}

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "HIGH"
        bridge._sandbox.cleanup()

    def test_thinking_level_minimal(self, tmp_path):
        """User selects 'Minimal' thinking level."""
        options = {"generation_config": {"thinking_level": "minimal"}}

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Temperature propagation
# =============================================================================


class TestTemperaturePropagation:
    """Verify temperature flows from UI to settings file."""

    def test_temperature_explicit(self, tmp_path):
        """User sets temperature via slider."""
        options = {"generation_config": {"temperature": 0.5}}

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["temperature"] == 0.5
        bridge._sandbox.cleanup()

    def test_temperature_default(self, tmp_path):
        """Default temperature should be 1.0 for Gemini 3."""
        options = {"generation_config": {"thinking_level": "high"}}

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["temperature"] == 1.0
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Combined options (thinking + temperature + max_tokens)
# =============================================================================


class TestCombinedOptions:
    """Verify multiple options work together."""

    def test_all_options_combined(self, tmp_path):
        """User changes thinking level, temperature, and max tokens."""
        options = {
            "generation_config": {
                "thinking_level": "medium",
                "temperature": 0.7,
                "max_output_tokens": 4096,
            }
        }

        bridge = _simulate_switch(options=options, working_dir=str(tmp_path))
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings)

        assert gen_cfg["thinkingConfig"]["thinkingLevel"] == "MEDIUM"
        assert gen_cfg["temperature"] == 0.7
        assert gen_cfg["maxOutputTokens"] == 4096
        # Default model → no customAliases, only customOverrides
        assert "customAliases" not in settings.get("modelConfigs", {})
        assert "model" not in settings  # No top-level model.name
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Response modalities for image models
# =============================================================================


class TestResponseModalities:
    """Verify response_modalities for image generation models."""

    def test_image_model_response_modalities(self, tmp_path):
        """Image model with response_modalities set."""
        options = {
            "generation_config": {
                "response_modalities": "TEXT,IMAGE",
            }
        }

        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options=options,
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings, model="gemini-3-pro-image-preview")

        assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
        # Image model is non-default → customAliases for routing
        alias = _get_alias(settings)
        assert alias["modelConfig"]["model"] == "gemini-3-pro-image-preview"
        # Image models should NOT have extends (no built-in alias)
        assert "extends" not in alias
        assert "model" not in settings  # No top-level model.name
        bridge._sandbox.cleanup()

    def test_response_modalities_as_list(self, tmp_path):
        """response_modalities can be passed as a list directly."""
        options = {
            "generation_config": {
                "response_modalities": ["TEXT", "IMAGE"],
            }
        }

        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options=options,
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings, model="gemini-3-pro-image-preview")

        assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
        bridge._sandbox.cleanup()

    def test_image_model_with_temperature(self, tmp_path):
        """Image model with response_modalities + temperature."""
        options = {
            "generation_config": {
                "response_modalities": "TEXT,IMAGE",
                "temperature": 0.9,
            }
        }

        bridge = _simulate_switch(
            model="gemini-2.5-flash-image",
            options=options,
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings, model="gemini-2.5-flash-image")

        assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
        assert gen_cfg["temperature"] == 0.9
        # Image model is non-default → customAliases for routing, no extends
        alias = _get_alias(settings)
        assert "extends" not in alias
        bridge._sandbox.cleanup()

    def test_image_model_ignores_thinking_level(self, tmp_path):
        """Image model must NOT include thinkingConfig even if thinking_level is passed.

        Image models don't support thinking — sending thinkingConfig causes
        "Internal error" from the API.
        """
        options = {
            "generation_config": {
                "response_modalities": "TEXT,IMAGE",
                "thinking_level": "high",
            }
        }

        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options=options,
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        gen_cfg = _get_gen_cfg(settings, model="gemini-3-pro-image-preview")

        assert gen_cfg["responseModalities"] == ["TEXT", "IMAGE"]
        assert "thinkingConfig" not in gen_cfg
        bridge._sandbox.cleanup()


# =============================================================================
# Test: model.name NEVER appears in ACP settings
# =============================================================================


class TestModelNameNeverInACP:
    """CRITICAL: model.name at top level causes 'Internal error' for
    non-standard models (bypasses the alias chain).

    Exception: when NO explicit model is set, model.name is written
    with 'gemini-3-pro-preview' to bypass the auto-gemini-3 classifier
    (which may route to Flash).  This is safe because gemini-3-pro-preview
    has a valid built-in alias chain.
    """

    def test_no_model_name_default_model(self, tmp_path):
        """Default model: no model.name in settings."""
        bridge = _simulate_switch(
            model="gemini-3-pro-preview",
            options={"generation_config": {"thinking_level": "high"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "model" not in settings
        bridge._sandbox.cleanup()

    def test_no_model_name_flash_model(self, tmp_path):
        """Flash model: no model.name in settings."""
        bridge = _simulate_switch(
            model="gemini-3-flash-preview",
            options={"generation_config": {"temperature": 0.5}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "model" not in settings
        bridge._sandbox.cleanup()

    def test_no_model_name_25_model(self, tmp_path):
        """Gemini 2.5 model: no model.name in settings."""
        bridge = _simulate_switch(
            model="gemini-2.5-flash",
            options={"generation_config": {"temperature": 0.8}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "model" not in settings
        bridge._sandbox.cleanup()

    def test_no_model_name_image_model(self, tmp_path):
        """Image model: no model.name in settings."""
        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options={"generation_config": {"response_modalities": "TEXT,IMAGE"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "model" not in settings
        bridge._sandbox.cleanup()

    def test_empty_model_has_default_model_name(self, tmp_path):
        """No model specified: model.name = gemini-3-pro-preview to bypass auto classifier."""
        bridge = _simulate_switch(
            model=None,
            options={"generation_config": {"thinking_level": "medium"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        # Empty model → force default Pro to bypass auto-gemini-3 classifier
        assert settings["model"]["name"] == "gemini-3-pro-preview"
        bridge._sandbox.cleanup()


# =============================================================================
# Test: extends chain correctness
# =============================================================================


class TestExtendsChain:
    """Verify the extends chain matches the model family.

    customAliases (with extends) are only written for non-default models.
    Default model (gemini-3-pro-preview) uses only customOverrides.

    Gemini CLI built-in alias chain:
        base → chat-base → chat-base-3  (Gemini 3: thinkingLevel)
                          → chat-base-2.5 (Gemini 2.5: thinkingBudget)
    """

    def test_gemini_3_pro_no_custom_aliases(self, tmp_path):
        """Default model → NO customAliases (built-in chain is sufficient)."""
        bridge = _simulate_switch(
            model="gemini-3-pro-preview",
            options={"generation_config": {"thinking_level": "high"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "customAliases" not in settings.get("modelConfigs", {})
        # But customOverrides should be present
        assert "customOverrides" in settings["modelConfigs"]
        bridge._sandbox.cleanup()

    def test_gemini_3_flash_extends_chat_base_3(self, tmp_path):
        """Non-default Gemini 3 model → customAliases with extends chat-base-3."""
        bridge = _simulate_switch(
            model="gemini-3-flash-preview",
            options={"generation_config": {"thinking_level": "low"}},
            working_dir=str(tmp_path),
        )
        alias = _get_alias(_read_settings(bridge))
        assert alias["extends"] == "chat-base-3"
        bridge._sandbox.cleanup()

    def test_gemini_25_extends_chat_base_25(self, tmp_path):
        bridge = _simulate_switch(
            model="gemini-2.5-flash",
            options={"generation_config": {"temperature": 0.5}},
            working_dir=str(tmp_path),
        )
        alias = _get_alias(_read_settings(bridge))
        assert alias["extends"] == "chat-base-2.5"
        bridge._sandbox.cleanup()

    def test_gemini_25_flash_lite_extends_chat_base_25(self, tmp_path):
        bridge = _simulate_switch(
            model="gemini-2.5-flash-lite",
            options={"generation_config": {"temperature": 0.8}},
            working_dir=str(tmp_path),
        )
        alias = _get_alias(_read_settings(bridge))
        assert alias["extends"] == "chat-base-2.5"
        bridge._sandbox.cleanup()

    def test_image_model_no_extends(self, tmp_path):
        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options={"generation_config": {"response_modalities": "TEXT,IMAGE"}},
            working_dir=str(tmp_path),
        )
        alias = _get_alias(_read_settings(bridge))
        assert "extends" not in alias
        bridge._sandbox.cleanup()

    def test_no_model_no_custom_aliases(self, tmp_path):
        """No model specified → default (gemini-3-pro-preview) → no customAliases."""
        bridge = _simulate_switch(
            model=None,
            options={"generation_config": {"thinking_level": "medium"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "customAliases" not in settings.get("modelConfigs", {})
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Alias model field (tells gemini-cli which API model to use)
# =============================================================================


class TestAliasModelField:
    """customAlias.modelConfig.model is for model routing (non-default models only).

    Default model (gemini-3-pro-preview) uses only customOverrides — no customAliases.
    Non-default models get customAliases for routing + customOverrides for config.
    """

    def test_default_model_no_alias(self, tmp_path):
        """Default model → NO customAliases (built-in chain handles it)."""
        bridge = _simulate_switch(
            model="gemini-3-pro-preview",
            options={"generation_config": {"thinking_level": "high"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "customAliases" not in settings.get("modelConfigs", {})
        # But customOverrides should match the default model
        overrides = settings["modelConfigs"]["customOverrides"]
        assert overrides[0]["match"]["model"] == "gemini-3-pro-preview"
        bridge._sandbox.cleanup()

    def test_different_model_in_alias(self, tmp_path):
        """When user selects gemini-2.5-flash, alias model must match."""
        bridge = _simulate_switch(
            model="gemini-2.5-flash",
            options={"generation_config": {"temperature": 0.5}},
            working_dir=str(tmp_path),
        )
        alias = _get_alias(_read_settings(bridge))
        assert alias["modelConfig"]["model"] == "gemini-2.5-flash"
        bridge._sandbox.cleanup()

    def test_no_model_no_alias(self, tmp_path):
        """No model → default (gemini-3-pro-preview) → no customAliases."""
        bridge = _simulate_switch(
            model=None,
            options={"generation_config": {"thinking_level": "low"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)
        assert "customAliases" not in settings.get("modelConfigs", {})
        # customOverrides should target the default model
        overrides = settings["modelConfigs"]["customOverrides"]
        assert overrides[0]["match"]["model"] == "gemini-3-pro-preview"
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Oneshot mode remains unchanged
# =============================================================================


class TestOneshotUnchanged:
    """Verify oneshot mode behavior is not affected by ACP changes."""

    def test_oneshot_has_model_name(self, tmp_path):
        """Oneshot mode should still set model.name at top level."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={"temperature": 0.7},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        settings = json.loads(bridge._gemini_settings_path.read_text())

        assert settings["model"]["name"] == "gemini-3-pro-preview"
        assert "modelConfigs" in settings
        bridge._sandbox.cleanup()

    def test_oneshot_no_extends(self, tmp_path):
        """Oneshot customAliases should NOT have extends (existing behavior)."""
        bridge = GeminiBridge(
            model="gemini-3-pro-preview",
            acp_enabled=False,
            generation_config={"thinking_level": "high"},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()
        settings = json.loads(bridge._gemini_settings_path.read_text())
        alias = settings["modelConfigs"]["customAliases"]["gemini-3-pro-preview"]

        # Oneshot uses existing behavior: no extends, no model in alias
        assert "extends" not in alias
        assert "model" not in alias.get("modelConfig", {})
        bridge._sandbox.cleanup()


# =============================================================================
# Test: No settings file when no config needed
# =============================================================================


class TestNoSettingsWhenNotNeeded:
    """Settings file should NOT be written when there's nothing to configure.

    Note: ACP mode ALWAYS generates settings (to bypass auto classifier
    and apply default thinkingConfig).  These tests cover oneshot mode
    and ACP edge cases.
    """

    def test_acp_always_generates_settings(self, tmp_path):
        """ACP always generates settings to bypass auto classifier."""
        bridge = GeminiBridge(
            acp_enabled=True,
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # ACP mode: settings MUST be generated even without explicit config
        assert bridge._gemini_settings_path is not None
        settings = json.loads(bridge._gemini_settings_path.read_text())
        assert settings["model"]["name"] == "gemini-3-pro-preview"
        assert "modelConfigs" in settings
        bridge._sandbox.cleanup()

    def test_acp_with_mcp_servers_generates_settings(self, tmp_path):
        """ACP with MCP servers also generates default settings."""
        bridge = GeminiBridge(
            acp_enabled=True,
            mcp_servers={"tools": {"command": "python", "args": ["t.py"]}},
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        assert bridge._gemini_settings_path is not None
        bridge._sandbox.cleanup()

    def test_only_system_prompt_acp(self, tmp_path):
        """ACP with only system prompt → settings file (for default model) + prompt file."""
        bridge = GeminiBridge(
            acp_enabled=True,
            system_prompt="Jsi avatar.",
            working_dir=str(tmp_path),
        )
        bridge._setup_config_files()

        # ACP always generates settings (to bypass auto classifier)
        assert bridge._gemini_settings_path is not None
        # System prompt file should also exist (separate mechanism)
        assert bridge._system_prompt_path is not None
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Settings file structure snapshot
# =============================================================================


class TestSettingsStructure:
    """Verify the exact JSON structure written to settings file.

    These snapshot tests catch unexpected structural changes that could
    cause gemini-cli to reject the config.
    """

    def test_full_acp_settings_structure_default_model(self, tmp_path):
        """Full ACP settings for default model: only customOverrides."""
        bridge = _simulate_switch(
            model="gemini-3-pro-preview",
            options={"generation_config": {"thinking_level": "medium", "temperature": 0.7}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)

        # Default model → no customAliases, only customOverrides + admin fast-start
        expected = {
            "admin": {
                "mcp": {"enabled": False},
                "extensions": {"enabled": False},
                "skills": {"enabled": False},
            },
            "modelConfigs": {
                "customOverrides": [
                    {
                        "match": {"model": "gemini-3-pro-preview"},
                        "modelConfig": {
                            "generateContentConfig": {
                                "temperature": 0.7,
                                "thinkingConfig": {
                                    "thinkingLevel": "MEDIUM",
                                },
                            },
                        },
                    }
                ]
            }
        }
        assert settings == expected
        bridge._sandbox.cleanup()

    def test_full_acp_settings_structure_non_default_model(self, tmp_path):
        """Full ACP settings for non-default model: customAliases + customOverrides."""
        bridge = _simulate_switch(
            model="gemini-2.5-flash",
            options={"generation_config": {"temperature": 0.5}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)

        expected = {
            "admin": {
                "mcp": {"enabled": False},
                "extensions": {"enabled": False},
                "skills": {"enabled": False},
            },
            "modelConfigs": {
                "customAliases": {
                    "gemini-3-pro-preview": {
                        "extends": "chat-base-2.5",
                        "modelConfig": {"model": "gemini-2.5-flash"},
                    }
                },
                "customOverrides": [
                    {
                        "match": {"model": "gemini-2.5-flash"},
                        "modelConfig": {
                            "generateContentConfig": {
                                "temperature": 0.5,
                            },
                        },
                    }
                ],
            }
        }
        assert settings == expected
        bridge._sandbox.cleanup()

    def test_full_image_model_settings_structure(self, tmp_path):
        """Full settings for image model: customAliases (routing) + customOverrides (config)."""
        bridge = _simulate_switch(
            model="gemini-3-pro-image-preview",
            options={"generation_config": {"response_modalities": "TEXT,IMAGE"}},
            working_dir=str(tmp_path),
        )
        settings = _read_settings(bridge)

        expected = {
            "admin": {
                "mcp": {"enabled": False},
                "extensions": {"enabled": False},
                "skills": {"enabled": False},
            },
            "modelConfigs": {
                "customAliases": {
                    "gemini-3-pro-preview": {
                        "modelConfig": {"model": "gemini-3-pro-image-preview"},
                    }
                },
                "customOverrides": [
                    {
                        "match": {"model": "gemini-3-pro-image-preview"},
                        "modelConfig": {
                            "generateContentConfig": {
                                "temperature": 1.0,
                                "responseModalities": ["TEXT", "IMAGE"],
                            },
                        },
                    }
                ],
            }
        }
        assert settings == expected
        bridge._sandbox.cleanup()

    def test_env_has_settings_path(self, tmp_path):
        """GEMINI_CLI_SYSTEM_SETTINGS_PATH must point to sandbox settings."""
        bridge = _simulate_switch(
            model="gemini-3-pro-preview",
            options={"generation_config": {"thinking_level": "high"}},
            working_dir=str(tmp_path),
        )
        env = bridge._build_subprocess_env()

        assert "GEMINI_CLI_SYSTEM_SETTINGS_PATH" in env
        settings_path = Path(env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"])
        assert settings_path.exists()
        # Settings file should be readable JSON
        data = json.loads(settings_path.read_text())
        assert "modelConfigs" in data
        bridge._sandbox.cleanup()


# =============================================================================
# Test: Engine creates bridge with correct generation_config
# =============================================================================


class TestEngineCreation:
    """Verify AvatarEngine._create_bridge() passes generation_config correctly.

    This tests the exact code path: AvatarEngine(**kwargs) → _create_bridge()
    → GeminiBridge(generation_config=pcfg.get("generation_config", {})).
    """

    def test_engine_passes_generation_config_to_bridge(self, tmp_path):
        """Engine should extract generation_config from kwargs and pass to bridge."""
        engine = AvatarEngine(
            provider="gemini",
            model="gemini-3-pro-preview",
            working_dir=str(tmp_path),
            generation_config={"thinking_level": "medium", "temperature": 0.5},
        )
        bridge = engine._create_bridge()

        assert isinstance(bridge, GeminiBridge)
        assert bridge.generation_config == {"thinking_level": "medium", "temperature": 0.5}
        assert bridge.acp_enabled is True

    def test_engine_empty_generation_config(self, tmp_path):
        """Engine with no generation_config should pass empty dict."""
        engine = AvatarEngine(
            provider="gemini",
            model="gemini-3-pro-preview",
            working_dir=str(tmp_path),
        )
        bridge = engine._create_bridge()

        assert isinstance(bridge, GeminiBridge)
        assert bridge.generation_config == {}

    def test_engine_response_modalities_in_generation_config(self, tmp_path):
        """response_modalities must be inside generation_config dict."""
        engine = AvatarEngine(
            provider="gemini",
            model="gemini-3-pro-image-preview",
            working_dir=str(tmp_path),
            generation_config={"response_modalities": "TEXT,IMAGE"},
        )
        bridge = engine._create_bridge()

        assert bridge.generation_config == {"response_modalities": "TEXT,IMAGE"}

    def test_engine_top_level_response_modalities_ignored(self, tmp_path):
        """response_modalities at top level (not in generation_config) is lost.

        This verifies the routing requirement: frontend must nest
        response_modalities inside generation_config.
        """
        engine = AvatarEngine(
            provider="gemini",
            model="gemini-3-pro-image-preview",
            working_dir=str(tmp_path),
            response_modalities="TEXT,IMAGE",  # WRONG: top level, not in generation_config
        )
        bridge = engine._create_bridge()

        # response_modalities is lost because engine extracts generation_config only
        assert bridge.generation_config == {}
        assert "response_modalities" not in bridge.generation_config
