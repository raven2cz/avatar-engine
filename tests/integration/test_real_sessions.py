"""
Integration tests for unified session management.

Tests session capabilities, listing, resume, and continue-last across providers.
Requires real CLI tools installed and authenticated.

Run with: pytest tests/integration/test_real_sessions.py -v
"""

import shutil

import pytest

from avatar_engine.bridges.base import BridgeState
from avatar_engine.bridges.codex import CodexBridge, _ACP_AVAILABLE
from avatar_engine.bridges.gemini import GeminiBridge
from avatar_engine.engine import AvatarEngine
from avatar_engine.types import SessionInfo, SessionCapabilitiesInfo


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def codex_acp_available():
    """Check if codex-acp is available via npx."""
    return shutil.which("npx") is not None and _ACP_AVAILABLE


@pytest.fixture
def skip_if_no_codex_acp(codex_acp_available):
    """Skip test if codex-acp is not available."""
    if not codex_acp_available:
        pytest.skip("codex-acp not available (npx or ACP SDK missing)")


@pytest.fixture(scope="session")
def gemini_available():
    """Check if Gemini CLI is available."""
    return shutil.which("gemini") is not None


@pytest.fixture
def skip_if_no_gemini(gemini_available):
    """Skip test if Gemini CLI not available."""
    if not gemini_available:
        pytest.skip("Gemini CLI not installed")


# =============================================================================
# Codex Session Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexSessionCapabilities:
    """Test session capabilities detected from codex-acp."""

    @pytest.mark.asyncio
    async def test_capabilities_detected(self, skip_if_no_codex_acp):
        """codex-acp should advertise load_session and list_sessions."""
        bridge = CodexBridge(timeout=30)
        try:
            await bridge.start()
            caps = bridge.session_capabilities

            assert caps.can_load is True, "codex-acp should support load_session"
            assert caps.can_list is True, "codex-acp should support list_sessions"
            assert caps.can_continue_last is True, "list + load = continue_last"
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_list_sessions(self, skip_if_no_codex_acp):
        """list_sessions should return SessionInfo objects."""
        bridge = CodexBridge(timeout=30)
        try:
            await bridge.start()
            sessions = await bridge.list_sessions()

            assert isinstance(sessions, list)
            for s in sessions:
                assert isinstance(s, SessionInfo)
                assert s.provider == "codex"
                assert len(s.session_id) > 0
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await bridge.stop()


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexSessionResume:
    """Test session resume and continue-last for Codex."""

    @pytest.mark.asyncio
    async def test_resume_nonexistent_falls_back(self, skip_if_no_codex_acp):
        """Resuming a nonexistent session should fall back to new session."""
        bridge = CodexBridge(resume_session_id="fake-nonexistent-id", timeout=30)
        try:
            await bridge.start()
            # Should have fallen back to new session
            assert bridge.state == BridgeState.READY
            assert bridge.session_id is not None
            assert bridge.session_id != "fake-nonexistent-id"

            response = await bridge.send("Say: OK")
            assert response.success is True
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_resume_real_session(self, skip_if_no_codex_acp):
        """Create a session, then resume it by ID."""
        # Phase 1: Create session
        bridge1 = CodexBridge(timeout=60)
        session_id = None
        try:
            await bridge1.start()
            session_id = bridge1.session_id
            assert session_id is not None

            r1 = await bridge1.send("Remember the code: AVATAR42")
            assert r1.success is True
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await bridge1.stop()

        # Phase 2: Resume same session
        bridge2 = CodexBridge(resume_session_id=session_id, timeout=60)
        try:
            await bridge2.start()
            assert bridge2.session_id == session_id

            r2 = await bridge2.send("What code did I ask you to remember?")
            assert r2.success is True
            assert "AVATAR42" in r2.content
        finally:
            await bridge2.stop()

    @pytest.mark.asyncio
    async def test_continue_last(self, skip_if_no_codex_acp):
        """continue_last should load most recent session."""
        # Phase 1: Create a session
        bridge1 = CodexBridge(timeout=60)
        try:
            await bridge1.start()
            first_session = bridge1.session_id
            await bridge1.send("Store marker: CONTINUE_TEST")
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await bridge1.stop()

        # Phase 2: Continue last session
        bridge2 = CodexBridge(continue_last=True, timeout=60)
        try:
            await bridge2.start()
            # Should have continued the previous session (or a recent one)
            assert bridge2.session_id is not None
            assert bridge2.state == BridgeState.READY
        finally:
            await bridge2.stop()


@pytest.mark.integration
@pytest.mark.codex
@pytest.mark.slow
class TestCodexSessionViaEngine:
    """Test session management through engine API."""

    @pytest.mark.asyncio
    async def test_engine_session_capabilities(self, skip_if_no_codex_acp):
        """Engine should expose bridge session capabilities."""
        engine = AvatarEngine(provider="codex", timeout=30)
        try:
            await engine.start()
            caps = engine.session_capabilities
            assert isinstance(caps, SessionCapabilitiesInfo)
            assert caps.can_load is True
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_list_sessions(self, skip_if_no_codex_acp):
        """Engine.list_sessions should return SessionInfo list."""
        engine = AvatarEngine(provider="codex", timeout=30)
        try:
            await engine.start()
            sessions = await engine.list_sessions()
            assert isinstance(sessions, list)
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_engine_resume_session(self, skip_if_no_codex_acp):
        """Engine.resume_session should work with valid session ID."""
        engine = AvatarEngine(provider="codex", timeout=60)
        try:
            await engine.start()
            original_id = engine.session_id

            # List sessions and try resuming one
            sessions = await engine.list_sessions()
            if not sessions:
                pytest.skip("No existing sessions to resume")

            target = sessions[0].session_id
            result = await engine.resume_session(target)
            assert result is True
        except Exception as e:
            if "auth" in str(e).lower() or "timed out" in str(e).lower():
                pytest.skip(f"Auth/timeout: {e}")
            raise
        finally:
            await engine.stop()


# =============================================================================
# Gemini Session Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestGeminiSessionCapabilities:
    """Test session capabilities detected from Gemini CLI via ACP."""

    @pytest.mark.asyncio
    async def test_capabilities_detected(self, skip_if_no_gemini):
        """Gemini ACP should detect session capabilities."""
        bridge = GeminiBridge(acp_enabled=True, timeout=30)
        try:
            await bridge.start()
            caps = bridge.session_capabilities
            # Capabilities depend on Gemini CLI version — just verify structure
            assert isinstance(caps, SessionCapabilitiesInfo)
        except Exception as e:
            if "fallback" in str(e).lower() or "acp" in str(e).lower():
                pytest.skip(f"ACP not available: {e}")
            raise
        finally:
            await bridge.stop()

    @pytest.mark.asyncio
    async def test_resume_nonexistent_falls_back(self, skip_if_no_gemini):
        """Gemini with fake resume_session_id should fall back to new session."""
        bridge = GeminiBridge(
            acp_enabled=True,
            resume_session_id="fake-gemini-session",
            timeout=30,
        )
        try:
            await bridge.start()
            assert bridge.state == BridgeState.READY
            assert bridge.session_id is not None
        except Exception as e:
            if "fallback" in str(e).lower() or "acp" in str(e).lower():
                pytest.skip(f"ACP not available: {e}")
            raise
        finally:
            await bridge.stop()
