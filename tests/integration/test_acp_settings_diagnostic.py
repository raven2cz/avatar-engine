"""Diagnostic: test different settings structures against real gemini-cli ACP.

Systematically tries different customAliases/overrides formats to find
which ones cause "Internal error" and which ones work.

Run with: pytest tests/integration/test_acp_settings_diagnostic.py -v -s
"""

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from avatar_engine.bridges.gemini import GeminiBridge

logger = logging.getLogger(__name__)

# Timeout per experiment
TIMEOUT = 120


class DiagnosticBridge(GeminiBridge):
    """Bridge that allows injecting custom settings for experiments."""

    def __init__(self, custom_settings: Dict[str, Any], **kwargs):
        self._custom_settings = custom_settings
        super().__init__(**kwargs)

    def _setup_config_files(self) -> None:
        """Override: write our custom settings instead of the generated ones."""
        from avatar_engine.config_sandbox import ConfigSandbox

        self._sandbox = ConfigSandbox()

        if self._custom_settings:
            self._gemini_settings_path = self._sandbox.write_gemini_settings(
                self._custom_settings
            )
        else:
            self._gemini_settings_path = None

        # System prompt → temp file for GEMINI_SYSTEM_MD env var
        if self.system_prompt:
            self._system_prompt_path = self._sandbox.write_system_prompt(
                self.system_prompt
            )
        else:
            self._system_prompt_path = None


async def run_experiment(
    name: str,
    settings: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run a single experiment: start ACP, send prompt, report result."""
    bridge = DiagnosticBridge(
        custom_settings=settings or {},
        acp_enabled=True,
        timeout=TIMEOUT,
    )

    result = {
        "name": name,
        "settings": settings,
        "acp_started": False,
        "prompt_success": False,
        "response": None,
        "error": None,
        "acp_mode": False,
    }

    try:
        await bridge.start()
        result["acp_started"] = True
        result["acp_mode"] = bridge._acp_mode

        if not bridge._acp_mode:
            result["error"] = "Not in ACP mode (fell back to oneshot before prompt)"
            return result

        response = await bridge.send("What is 2+2? Just the number.")
        result["prompt_success"] = response.success
        result["response"] = response.content if response.success else None
        result["error"] = response.error if not response.success else None

        # Check if we're still in ACP mode after the prompt
        result["acp_mode_after"] = bridge._acp_mode

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await bridge.stop()

    return result


def print_result(r: Dict[str, Any]) -> None:
    """Print experiment result in a readable format."""
    status = "PASS" if r["prompt_success"] and r.get("acp_mode_after", False) else "FAIL"
    print(f"\n{'='*60}")
    print(f"[{status}] {r['name']}")
    print(f"  ACP started: {r['acp_started']}")
    print(f"  ACP mode: {r['acp_mode']}")
    print(f"  Prompt success: {r['prompt_success']}")
    if r.get("acp_mode_after") is not None:
        print(f"  ACP mode after: {r['acp_mode_after']}")
    if r["response"]:
        print(f"  Response: {r['response'][:100]}")
    if r["error"]:
        print(f"  Error: {r['error']}")
    if r["settings"]:
        print(f"  Settings: {json.dumps(r['settings'], indent=2)[:300]}")
    else:
        print(f"  Settings: (none)")


# =============================================================================
# Experiments
# =============================================================================

EXPERIMENTS = {
    # Baseline: no settings at all (should work)
    "A_no_settings": None,

    # Experiment B: customAliases with extends + model (current implementation)
    "B_extends_and_model": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "extends": "chat-base-3",
                    "modelConfig": {
                        "model": "gemini-3-pro-preview",
                        "generateContentConfig": {
                            "temperature": 1.0,
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            }
        }
    },

    # Experiment C: customAliases WITHOUT extends, WITHOUT model
    # (matches documentation example format)
    "C_no_extends_no_model": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            }
        }
    },

    # Experiment D: customAliases WITH extends, WITHOUT model
    "D_extends_no_model": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "extends": "chat-base-3",
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            }
        }
    },

    # Experiment E: customAliases WITHOUT extends, WITH model
    "E_no_extends_with_model": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "modelConfig": {
                        "model": "gemini-3-pro-preview",
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            }
        }
    },

    # Experiment F: just temperature, no thinkingConfig
    "F_just_temperature": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "modelConfig": {
                        "generateContentConfig": {
                            "temperature": 0.5
                        }
                    }
                }
            }
        }
    },

    # Experiment G: overrides as object (WRONG format — should be array)
    "G_overrides_object_WRONG": {
        "modelConfigs": {
            "overrides": {
                "gemini-3-pro-preview": {
                    "generateContentConfig": {
                        "thinkingConfig": {
                            "thinkingLevel": "MEDIUM"
                        }
                    }
                }
            }
        }
    },

    # Experiment H: empty modelConfigs (just the key)
    "H_empty_model_configs": {
        "modelConfigs": {}
    },

    # Experiment I: empty settings object
    "I_empty_settings": {},

    # =============================================
    # NEW EXPERIMENTS: customOverrides (array format)
    # =============================================

    # Experiment J: customOverrides with thinkingLevel
    "J_customOverrides_thinking": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment K: customOverrides with temperature
    "K_customOverrides_temperature": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "temperature": 0.5
                        }
                    }
                }
            ]
        }
    },

    # Experiment L: customOverrides with both thinking + temperature
    "L_customOverrides_combined": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "temperature": 0.5,
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment M: customAliases with extends+model but NO generateContentConfig
    # (to isolate if the issue is with generateContentConfig itself)
    "M_alias_extends_model_only": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "extends": "chat-base-3",
                    "modelConfig": {
                        "model": "gemini-3-pro-preview"
                    }
                }
            }
        }
    },

    # Experiment O: thinkingLevel=HIGH (same as default) — to test if ANY thinkingConfig override fails
    "O_thinking_high_default": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "HIGH"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment P: only includeThoughts (no thinkingLevel)
    "P_include_thoughts_only": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "includeThoughts": True
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment Q: thinkingLevel=LOW
    "Q_thinking_low": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "LOW"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment R: customOverrides with LOW + temperature (valid for Pro)
    "R_customOverrides_low_plus_temp": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "temperature": 0.5,
                            "thinkingConfig": {
                                "thinkingLevel": "LOW"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment S: customAliases with extends+model+LOW (test if customAliases work with valid level)
    "S_alias_with_low": {
        "modelConfigs": {
            "customAliases": {
                "gemini-3-pro-preview": {
                    "extends": "chat-base-3",
                    "modelConfig": {
                        "model": "gemini-3-pro-preview",
                        "generateContentConfig": {
                            "temperature": 1.0,
                            "thinkingConfig": {
                                "thinkingLevel": "LOW"
                            }
                        }
                    }
                }
            }
        }
    },

    # Experiment T: customOverrides MINIMAL (for Pro)
    "T_thinking_minimal": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MINIMAL"
                            }
                        }
                    }
                }
            ]
        }
    },

    # Experiment N: customOverrides with responseModalities for image model
    "N_customOverrides_image": {
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "gemini-3-pro-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": "MEDIUM"
                            }
                        }
                    }
                },
                {
                    "match": {"model": "gemini-3-pro-image-preview"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "responseModalities": ["TEXT", "IMAGE"]
                        }
                    }
                }
            ]
        }
    },
}


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestACPSettingsDiagnostic:
    """Systematic diagnostic of which settings structures work in ACP mode."""

    @pytest.mark.asyncio
    async def test_A_no_settings(self, skip_if_no_gemini):
        """Baseline: no settings file → should work in ACP."""
        r = await run_experiment("A_no_settings", EXPERIMENTS["A_no_settings"])
        print_result(r)
        assert r["prompt_success"], f"Baseline failed: {r['error']}"

    @pytest.mark.asyncio
    async def test_B_extends_and_model(self, skip_if_no_gemini):
        """Current implementation: extends + model in customAliases."""
        r = await run_experiment("B_extends_and_model", EXPERIMENTS["B_extends_and_model"])
        print_result(r)
        # This is our current implementation — we want to know if it works

    @pytest.mark.asyncio
    async def test_C_no_extends_no_model(self, skip_if_no_gemini):
        """Documentation format: just generateContentConfig."""
        r = await run_experiment("C_no_extends_no_model", EXPERIMENTS["C_no_extends_no_model"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_D_extends_no_model(self, skip_if_no_gemini):
        """With extends but without modelConfig.model."""
        r = await run_experiment("D_extends_no_model", EXPERIMENTS["D_extends_no_model"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_E_no_extends_with_model(self, skip_if_no_gemini):
        """Without extends but with modelConfig.model."""
        r = await run_experiment("E_no_extends_with_model", EXPERIMENTS["E_no_extends_with_model"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_F_just_temperature(self, skip_if_no_gemini):
        """Minimal: just temperature change."""
        r = await run_experiment("F_just_temperature", EXPERIMENTS["F_just_temperature"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_G_overrides(self, skip_if_no_gemini):
        """Use modelConfigs.overrides instead of customAliases."""
        r = await run_experiment("G_overrides_object_WRONG", EXPERIMENTS["G_overrides_object_WRONG"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_H_empty_model_configs(self, skip_if_no_gemini):
        """Empty modelConfigs (should be like no settings)."""
        r = await run_experiment("H_empty_model_configs", EXPERIMENTS["H_empty_model_configs"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_I_empty_settings(self, skip_if_no_gemini):
        """Empty settings object (should be like no settings)."""
        r = await run_experiment("I_empty_settings", EXPERIMENTS["I_empty_settings"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_J_customOverrides_thinking(self, skip_if_no_gemini):
        """customOverrides (array) with thinkingLevel — should preserve alias chain."""
        r = await run_experiment("J_customOverrides_thinking", EXPERIMENTS["J_customOverrides_thinking"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_K_customOverrides_temperature(self, skip_if_no_gemini):
        """customOverrides (array) with temperature."""
        r = await run_experiment("K_customOverrides_temperature", EXPERIMENTS["K_customOverrides_temperature"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_L_customOverrides_combined(self, skip_if_no_gemini):
        """customOverrides (array) with thinking + temperature."""
        r = await run_experiment("L_customOverrides_combined", EXPERIMENTS["L_customOverrides_combined"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_M_alias_extends_model_only(self, skip_if_no_gemini):
        """customAliases with extends + model but NO generateContentConfig."""
        r = await run_experiment("M_alias_extends_model_only", EXPERIMENTS["M_alias_extends_model_only"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_N_customOverrides_image(self, skip_if_no_gemini):
        """customOverrides with thinking + image model responseModalities."""
        r = await run_experiment("N_customOverrides_image", EXPERIMENTS["N_customOverrides_image"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_O_thinking_high_default(self, skip_if_no_gemini):
        """Override thinkingLevel to HIGH (same as default) — isolates thinkingConfig issue."""
        r = await run_experiment("O_thinking_high_default", EXPERIMENTS["O_thinking_high_default"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_P_include_thoughts_only(self, skip_if_no_gemini):
        """Override just includeThoughts (no thinkingLevel) — isolates thinkingLevel."""
        r = await run_experiment("P_include_thoughts_only", EXPERIMENTS["P_include_thoughts_only"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_Q_thinking_low(self, skip_if_no_gemini):
        """Override thinkingLevel to LOW."""
        r = await run_experiment("Q_thinking_low", EXPERIMENTS["Q_thinking_low"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_R_customOverrides_low_plus_temp(self, skip_if_no_gemini):
        """customOverrides: LOW + temperature (both valid for Pro)."""
        r = await run_experiment("R_customOverrides_low_plus_temp", EXPERIMENTS["R_customOverrides_low_plus_temp"])
        print_result(r)
        assert r["prompt_success"] and r.get("acp_mode_after", False), f"Expected ACP_OK: {r['error']}"

    @pytest.mark.asyncio
    async def test_S_alias_with_low(self, skip_if_no_gemini):
        """customAliases with extends+model+LOW — tests if customAliases work with valid level."""
        r = await run_experiment("S_alias_with_low", EXPERIMENTS["S_alias_with_low"])
        print_result(r)

    @pytest.mark.asyncio
    async def test_T_thinking_minimal(self, skip_if_no_gemini):
        """Override thinkingLevel to MINIMAL (valid for Pro)."""
        r = await run_experiment("T_thinking_minimal", EXPERIMENTS["T_thinking_minimal"])
        print_result(r)
        assert r["prompt_success"] and r.get("acp_mode_after", False), f"Expected ACP_OK: {r['error']}"


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestACPSettingsAllAtOnce:
    """Run all experiments sequentially and print summary."""

    @pytest.mark.asyncio
    async def test_all_experiments(self, skip_if_no_gemini):
        """Run ALL experiments and print comparative results."""
        results = []
        for name, settings in EXPERIMENTS.items():
            print(f"\n--- Running experiment: {name} ---")
            r = await run_experiment(name, settings)
            print_result(r)
            results.append(r)
            # Brief pause between experiments to avoid rate limiting
            await asyncio.sleep(2)

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for r in results:
            acp_ok = r["prompt_success"] and r.get("acp_mode_after", False)
            fallback = r["prompt_success"] and not r.get("acp_mode_after", False)
            status = "ACP_OK" if acp_ok else ("FALLBACK" if fallback else "FAIL")
            print(f"  [{status:8s}] {r['name']}")

        # At least the baseline should work
        baseline = results[0]
        assert baseline["prompt_success"], f"Baseline failed: {baseline['error']}"
