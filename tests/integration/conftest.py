"""
Integration test fixtures and configuration.

These tests require real CLI tools installed and configured.
"""

import asyncio
import shutil
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires real CLI)"
    )
    config.addinivalue_line(
        "markers", "claude: mark test as requiring Claude CLI"
    )
    config.addinivalue_line(
        "markers", "gemini: mark test as requiring Gemini CLI"
    )
    config.addinivalue_line(
        "markers", "codex: mark test as requiring Codex CLI (codex-acp)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow (API calls)"
    )


@pytest.fixture(scope="session")
def claude_available():
    """Check if Claude CLI is available."""
    return shutil.which("claude") is not None


@pytest.fixture(scope="session")
def gemini_available():
    """Check if Gemini CLI is available."""
    return shutil.which("gemini") is not None


@pytest.fixture
def skip_if_no_claude(claude_available):
    """Skip test if Claude CLI not available."""
    if not claude_available:
        pytest.skip("Claude CLI not installed")


@pytest.fixture
def skip_if_no_gemini(gemini_available):
    """Skip test if Gemini CLI not available."""
    if not gemini_available:
        pytest.skip("Gemini CLI not installed")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
