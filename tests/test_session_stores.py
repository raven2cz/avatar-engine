"""Tests for filesystem session stores (Gemini + Claude + Codex).

Tests use tmp_path fixture — no real ~/.gemini, ~/.claude, or ~/.codex needed.
"""

import json
import time
from pathlib import Path

import pytest

from avatar_engine.sessions import get_session_store, SessionStore
from avatar_engine.sessions._gemini import GeminiFileSessionStore
from avatar_engine.sessions._claude import ClaudeFileSessionStore
from avatar_engine.sessions._codex import CodexFileSessionStore
from avatar_engine.types import SessionInfo


# =============================================================================
# Factory tests
# =============================================================================


class TestGetSessionStore:
    def test_gemini(self):
        store = get_session_store("gemini")
        assert isinstance(store, GeminiFileSessionStore)

    def test_claude(self):
        store = get_session_store("claude")
        assert isinstance(store, ClaudeFileSessionStore)

    def test_codex(self):
        store = get_session_store("codex")
        assert isinstance(store, CodexFileSessionStore)

    def test_unknown_returns_none(self):
        assert get_session_store("openai") is None


# =============================================================================
# GeminiFileSessionStore tests
# =============================================================================


class TestGeminiFileSessionStore:
    """Tests for Gemini filesystem session store."""

    def _make_store(self, tmp_path: Path) -> GeminiFileSessionStore:
        return GeminiFileSessionStore(gemini_home=tmp_path)

    def _session_dir(self, tmp_path: Path, working_dir: str) -> Path:
        """Create and return the chats directory for a working dir."""
        h = GeminiFileSessionStore._compute_project_hash(working_dir)
        chats = tmp_path / h / "chats"
        chats.mkdir(parents=True, exist_ok=True)
        return chats

    def test_compute_project_hash(self):
        """Hash should be deterministic SHA-256 of the path string."""
        import hashlib
        path = "/home/user/project"
        expected = hashlib.sha256(path.encode()).hexdigest()
        assert GeminiFileSessionStore._compute_project_hash(path) == expected

    @pytest.mark.asyncio
    async def test_empty_dir(self, tmp_path):
        """No chats directory → empty list."""
        store = self._make_store(tmp_path)
        result = await store.list_sessions("/home/user/project")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_session(self, tmp_path):
        """Parse a single valid session file."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/home/user/project")

        data = {
            "sessionId": "gem-001",
            "lastUpdated": "2025-06-15T10:30:00Z",
            "messages": [
                {"type": "user", "content": "Debugging auth flow"},
            ],
        }
        (chats / "session-gem-001.json").write_text(json.dumps(data))

        result = await store.list_sessions("/home/user/project")
        assert len(result) == 1
        assert result[0].session_id == "gem-001"
        assert result[0].provider == "gemini"
        assert result[0].title == "Debugging auth flow"
        assert result[0].updated_at == "2025-06-15T10:30:00Z"

    @pytest.mark.asyncio
    async def test_title_from_first_user_message(self, tmp_path):
        """Title from first user message content."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        data = {
            "sessionId": "gem-002",
            "messages": [
                {"type": "user", "content": "Explain the auth module"},
                {"type": "gemini", "content": "Sure..."},
            ],
        }
        (chats / "session-gem-002.json").write_text(json.dumps(data))

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 1
        assert result[0].title == "Explain the auth module"

    @pytest.mark.asyncio
    async def test_fallback_to_start_time(self, tmp_path):
        """updated_at falls back to startTime when lastUpdated missing."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        data = {
            "sessionId": "gem-003",
            "startTime": "2025-06-01T08:00:00Z",
            "messages": [],
        }
        (chats / "session-gem-003.json").write_text(json.dumps(data))

        result = await store.list_sessions("/tmp/test")
        assert result[0].updated_at == "2025-06-01T08:00:00Z"

    @pytest.mark.asyncio
    async def test_multiple_sessions_sorted(self, tmp_path):
        """Multiple sessions should be sorted by updated_at desc."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        for i, ts in enumerate(["2025-01-01", "2025-06-15", "2025-03-10"]):
            data = {
                "sessionId": f"gem-{i}",
                "lastUpdated": ts,
                "messages": [],
            }
            (chats / f"session-gem-{i}.json").write_text(json.dumps(data))

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 3
        assert result[0].updated_at == "2025-06-15"
        assert result[1].updated_at == "2025-03-10"
        assert result[2].updated_at == "2025-01-01"

    @pytest.mark.asyncio
    async def test_invalid_json_skipped(self, tmp_path):
        """Invalid JSON files should be silently skipped."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        (chats / "session-bad.json").write_text("not json at all")
        data = {"sessionId": "gem-ok", "messages": []}
        (chats / "session-ok.json").write_text(json.dumps(data))

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 1
        assert result[0].session_id == "gem-ok"

    @pytest.mark.asyncio
    async def test_missing_session_id_skipped(self, tmp_path):
        """Session file without sessionId should be skipped."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        data = {"summary": "No ID", "messages": []}
        (chats / "session-noid.json").write_text(json.dumps(data))

        result = await store.list_sessions("/tmp/test")
        assert result == []

    @pytest.mark.asyncio
    async def test_different_working_dirs_isolated(self, tmp_path):
        """Sessions from different working dirs should not mix."""
        store = self._make_store(tmp_path)

        chats_a = self._session_dir(tmp_path, "/project-a")
        chats_b = self._session_dir(tmp_path, "/project-b")

        (chats_a / "session-a1.json").write_text(
            json.dumps({"sessionId": "a1", "messages": []})
        )
        (chats_b / "session-b1.json").write_text(
            json.dumps({"sessionId": "b1", "messages": []})
        )

        result_a = await store.list_sessions("/project-a")
        result_b = await store.list_sessions("/project-b")

        assert len(result_a) == 1
        assert result_a[0].session_id == "a1"
        assert len(result_b) == 1
        assert result_b[0].session_id == "b1"


# =============================================================================
# ClaudeFileSessionStore tests
# =============================================================================


class TestClaudeFileSessionStore:
    """Tests for Claude filesystem session store."""

    def _make_store(self, tmp_path: Path) -> ClaudeFileSessionStore:
        return ClaudeFileSessionStore(claude_home=tmp_path)

    def _session_dir(self, tmp_path: Path, working_dir: str) -> Path:
        """Create and return the project directory for a working dir."""
        encoded = ClaudeFileSessionStore._encode_path(working_dir)
        project = tmp_path / encoded
        project.mkdir(parents=True, exist_ok=True)
        return project

    def test_encode_path(self):
        """Path encoding should replace / with -."""
        assert ClaudeFileSessionStore._encode_path("/home/box/git/project") == "-home-box-git-project"
        assert ClaudeFileSessionStore._encode_path("/tmp") == "-tmp"

    @pytest.mark.asyncio
    async def test_empty_dir(self, tmp_path):
        """No project directory → empty list."""
        store = self._make_store(tmp_path)
        result = await store.list_sessions("/home/user/project")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_session(self, tmp_path):
        """Parse a single valid JSONL session file."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/home/user/project")

        events = [
            {"type": "system", "subtype": "init", "session_id": "uuid-001"},
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Fix the login bug"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Sure, let me look..."}],
                },
            },
        ]
        session_file = project / "uuid-001.jsonl"
        session_file.write_text("\n".join(json.dumps(e) for e in events))

        result = await store.list_sessions("/home/user/project")
        assert len(result) == 1
        assert result[0].session_id == "uuid-001"
        assert result[0].provider == "claude"
        assert result[0].title == "Fix the login bug"
        assert result[0].updated_at is not None  # mtime-based

    @pytest.mark.asyncio
    async def test_skips_interrupted_messages(self, tmp_path):
        """Should skip [Request interrupted...] messages for title."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "[Request interrupted by user]"}
                    ],
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Real question here"}
                    ],
                },
            },
        ]
        (project / "uuid-skip.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        result = await store.list_sessions("/tmp/test")
        assert result[0].title == "Real question here"

    @pytest.mark.asyncio
    async def test_no_user_message_title_is_none(self, tmp_path):
        """Session with no user messages should have title=None."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {"type": "system", "subtype": "init", "session_id": "uuid-nouse"},
        ]
        (project / "uuid-nouse.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        result = await store.list_sessions("/tmp/test")
        assert result[0].title is None

    @pytest.mark.asyncio
    async def test_multiple_sessions_sorted_by_mtime(self, tmp_path):
        """Multiple sessions sorted by file mtime (newest first)."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        # Create files with different mtimes
        for i, name in enumerate(["old", "new", "mid"]):
            f = project / f"uuid-{name}.jsonl"
            f.write_text(json.dumps({"type": "system"}) + "\n")

        # Set mtimes explicitly
        import os
        now = time.time()
        os.utime(project / "uuid-old.jsonl", (now - 300, now - 300))
        os.utime(project / "uuid-mid.jsonl", (now - 100, now - 100))
        os.utime(project / "uuid-new.jsonl", (now, now))

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 3
        assert result[0].session_id == "uuid-new"
        assert result[2].session_id == "uuid-old"

    @pytest.mark.asyncio
    async def test_empty_file_skipped(self, tmp_path):
        """Empty JSONL file should still produce a session (with title=None)."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        (project / "uuid-empty.jsonl").write_text("")

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 1
        assert result[0].session_id == "uuid-empty"
        assert result[0].title is None

    @pytest.mark.asyncio
    async def test_different_working_dirs_isolated(self, tmp_path):
        """Sessions from different working dirs should not mix."""
        store = self._make_store(tmp_path)

        proj_a = self._session_dir(tmp_path, "/project-a")
        proj_b = self._session_dir(tmp_path, "/project-b")

        (proj_a / "a1.jsonl").write_text(json.dumps({"type": "system"}) + "\n")
        (proj_b / "b1.jsonl").write_text(json.dumps({"type": "system"}) + "\n")

        result_a = await store.list_sessions("/project-a")
        result_b = await store.list_sessions("/project-b")

        assert len(result_a) == 1
        assert result_a[0].session_id == "a1"
        assert len(result_b) == 1
        assert result_b[0].session_id == "b1"

    @pytest.mark.asyncio
    async def test_non_jsonl_files_ignored(self, tmp_path):
        """Non-.jsonl files should be ignored."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        (project / "summary.md").write_text("# Summary")
        (project / "uuid-real.jsonl").write_text(
            json.dumps({"type": "system"}) + "\n"
        )

        result = await store.list_sessions("/tmp/test")
        assert len(result) == 1
        assert result[0].session_id == "uuid-real"

    @pytest.mark.asyncio
    async def test_title_truncated_at_80_chars(self, tmp_path):
        """Long titles should be truncated to 80 characters."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        long_text = "A" * 200
        events = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": long_text}],
                },
            },
        ]
        (project / "uuid-long.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        result = await store.list_sessions("/tmp/test")
        assert len(result[0].title) == 80


# =============================================================================
# GeminiFileSessionStore._find_session_file() + load_session_messages() tests
#
# Gemini CLI filenames use: session-{timestamp}-{shortId}.json
# e.g. session-2026-02-09T05-53-fa4de119.json
# The full UUID (fa4de119-4771-481b-908f-dd15fde55a86) is only inside the JSON.
# =============================================================================


class TestGeminiLoadSessionMessages:
    """Tests for loading messages from Gemini session files.

    Uses realistic timestamp-based filenames matching real Gemini CLI output.
    """

    def _make_store(self, tmp_path: Path) -> GeminiFileSessionStore:
        return GeminiFileSessionStore(gemini_home=tmp_path)

    def _session_dir(self, tmp_path: Path, working_dir: str) -> Path:
        h = GeminiFileSessionStore._compute_project_hash(working_dir)
        chats = tmp_path / h / "chats"
        chats.mkdir(parents=True, exist_ok=True)
        return chats

    def test_find_session_by_short_id_suffix(self, tmp_path):
        """_find_session_file should match by short-ID suffix in filename."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        full_id = "fa4de119-4771-481b-908f-dd15fde55a86"
        data = {"sessionId": full_id, "messages": []}
        # Realistic filename: session-{timestamp}-{shortId}.json
        (chats / "session-2026-02-09T05-53-fa4de119.json").write_text(json.dumps(data))

        found = store._find_session_file(full_id, "/tmp/test")
        assert found is not None
        assert found.name == "session-2026-02-09T05-53-fa4de119.json"

    def test_find_session_fallback_scan(self, tmp_path):
        """_find_session_file should fall back to scanning all files."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        # Filename that does NOT end with the short ID (unusual naming)
        full_id = "abc12345-6789-4000-a000-000000000001"
        data = {"sessionId": full_id, "messages": []}
        (chats / "session-2026-02-09T10-00-zzzzunrelated.json").write_text(json.dumps(data))

        found = store._find_session_file(full_id, "/tmp/test")
        assert found is not None

    def test_find_session_not_found(self, tmp_path):
        """_find_session_file returns None when session doesn't exist."""
        store = self._make_store(tmp_path)
        self._session_dir(tmp_path, "/tmp/test")  # create empty dir

        found = store._find_session_file("nonexistent-id", "/tmp/test")
        assert found is None

    def test_find_session_no_chats_dir(self, tmp_path):
        """_find_session_file returns None when chats dir missing."""
        store = self._make_store(tmp_path)
        found = store._find_session_file("any-id", "/tmp/test")
        assert found is None

    def test_load_messages_with_timestamp_filename(self, tmp_path):
        """Load messages from a session file with realistic timestamp filename."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        full_id = "fa4de119-4771-481b-908f-dd15fde55a86"
        data = {
            "sessionId": full_id,
            "messages": [
                {"type": "user", "content": "Hello Gemini"},
                {"type": "gemini", "content": "Hello! How can I help?"},
                {"type": "user", "content": "Fix the bug"},
                {"type": "gemini", "content": "Sure, let me look at it."},
            ],
        }
        (chats / "session-2026-02-09T05-53-fa4de119.json").write_text(json.dumps(data))

        messages = store.load_session_messages(full_id, "/tmp/test")
        assert len(messages) == 4
        assert messages[0].role == "user"
        assert messages[0].content == "Hello Gemini"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Hello! How can I help?"
        assert messages[2].role == "user"
        assert messages[3].role == "assistant"

    def test_load_messages_not_found(self, tmp_path):
        """Non-existent session returns empty list."""
        store = self._make_store(tmp_path)
        messages = store.load_session_messages("nonexistent", "/tmp/test")
        assert messages == []

    def test_load_messages_skips_empty_content(self, tmp_path):
        """Messages with empty content should be skipped."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        full_id = "b1111111-2222-3333-4444-555555555555"
        data = {
            "sessionId": full_id,
            "messages": [
                {"type": "user", "content": "Hello"},
                {"type": "gemini", "content": ""},
                {"type": "user", "content": "   "},
                {"type": "gemini", "content": "Real response"},
            ],
        }
        (chats / "session-2026-02-09T06-00-b1111111.json").write_text(json.dumps(data))

        messages = store.load_session_messages(full_id, "/tmp/test")
        assert len(messages) == 2
        assert messages[0].content == "Hello"
        assert messages[1].content == "Real response"

    def test_load_messages_skips_error_type(self, tmp_path):
        """Error-type messages should be skipped."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        full_id = "c2222222-3333-4444-5555-666666666666"
        data = {
            "sessionId": full_id,
            "messages": [
                {"type": "user", "content": "Do something"},
                {"type": "error", "content": "Something went wrong"},
                {"type": "gemini", "content": "Let me try again"},
            ],
        }
        (chats / "session-2026-02-09T07-00-c2222222.json").write_text(json.dumps(data))

        messages = store.load_session_messages(full_id, "/tmp/test")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_load_messages_invalid_json(self, tmp_path):
        """Invalid JSON returns empty list (file found by fallback scan, but unparseable)."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        # Can't find by ID because content is invalid — returns empty
        (chats / "session-2026-02-09T08-00-deadbeef.json").write_text("not json")

        messages = store.load_session_messages("deadbeef-0000-0000-0000-000000000000", "/tmp/test")
        assert messages == []

    def test_load_messages_no_messages_key(self, tmp_path):
        """Session file without messages key returns empty list."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        full_id = "d3333333-4444-5555-6666-777777777777"
        data = {"sessionId": full_id}
        (chats / "session-2026-02-09T09-00-d3333333.json").write_text(json.dumps(data))

        messages = store.load_session_messages(full_id, "/tmp/test")
        assert messages == []

    def test_load_messages_multiple_files_picks_correct(self, tmp_path):
        """With multiple files, should pick the one with matching sessionId."""
        store = self._make_store(tmp_path)
        chats = self._session_dir(tmp_path, "/tmp/test")

        target_id = "e4444444-5555-6666-7777-888888888888"
        other_id = "f5555555-6666-7777-8888-999999999999"

        data_target = {
            "sessionId": target_id,
            "messages": [{"type": "user", "content": "Target session"}],
        }
        data_other = {
            "sessionId": other_id,
            "messages": [{"type": "user", "content": "Other session"}],
        }
        (chats / "session-2026-02-09T10-00-e4444444.json").write_text(json.dumps(data_target))
        (chats / "session-2026-02-09T10-30-f5555555.json").write_text(json.dumps(data_other))

        messages = store.load_session_messages(target_id, "/tmp/test")
        assert len(messages) == 1
        assert messages[0].content == "Target session"


# =============================================================================
# ClaudeFileSessionStore.load_session_messages() tests
# =============================================================================


class TestClaudeLoadSessionMessages:
    """Tests for loading messages from Claude JSONL session files."""

    def _make_store(self, tmp_path: Path) -> ClaudeFileSessionStore:
        return ClaudeFileSessionStore(claude_home=tmp_path)

    def _session_dir(self, tmp_path: Path, working_dir: str) -> Path:
        encoded = ClaudeFileSessionStore._encode_path(working_dir)
        project = tmp_path / encoded
        project.mkdir(parents=True, exist_ok=True)
        return project

    def test_load_messages_basic(self, tmp_path):
        """Load messages from a valid Claude JSONL session file."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {"type": "system", "subtype": "init", "session_id": "uuid-001"},
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Fix the login bug"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Sure, let me look..."}],
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Thanks!"}],
                },
            },
        ]
        (project / "uuid-001.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages("uuid-001", "/tmp/test")
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Fix the login bug"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Sure, let me look..."
        assert messages[2].role == "user"
        assert messages[2].content == "Thanks!"

    def test_load_messages_not_found(self, tmp_path):
        """Non-existent session returns empty list."""
        store = self._make_store(tmp_path)
        messages = store.load_session_messages("nonexistent", "/tmp/test")
        assert messages == []

    def test_load_messages_skips_system_events(self, tmp_path):
        """System events should be skipped."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {"type": "system", "subtype": "init", "session_id": "uuid-sys"},
            {"type": "tool_use", "tool_name": "read_file"},
            {"type": "result", "result": "done"},
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Hello"}],
                },
            },
        ]
        (project / "uuid-sys.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages("uuid-sys", "/tmp/test")
        assert len(messages) == 1
        assert messages[0].content == "Hello"

    def test_load_messages_string_content(self, tmp_path):
        """Handle string content (not list of blocks)."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Simple string"},
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": "Response string"},
            },
        ]
        (project / "uuid-str.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages("uuid-str", "/tmp/test")
        assert len(messages) == 2
        assert messages[0].content == "Simple string"
        assert messages[1].content == "Response string"

    def test_load_messages_empty_content_skipped(self, tmp_path):
        """Empty content messages should be skipped."""
        store = self._make_store(tmp_path)
        project = self._session_dir(tmp_path, "/tmp/test")

        events = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Real message"}],
                },
            },
            {
                "type": "assistant",
                "message": {"role": "assistant", "content": ""},
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": ""}],
                },
            },
        ]
        (project / "uuid-empty.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages("uuid-empty", "/tmp/test")
        assert len(messages) == 1
        assert messages[0].content == "Real message"


# =============================================================================
# CodexFileSessionStore tests
#
# Codex CLI stores sessions at:
#   ~/.codex/sessions/YYYY/MM/DD/rollout-{timestamp}-{sessionId}.jsonl
# =============================================================================


class TestCodexFileSessionStore:
    """Tests for Codex filesystem session store."""

    def _make_store(self, tmp_path: Path) -> CodexFileSessionStore:
        return CodexFileSessionStore(codex_home=tmp_path)

    def _make_session_file(
        self, tmp_path: Path, session_id: str, cwd: str, messages: list
    ) -> Path:
        """Create a realistic Codex session JSONL file."""
        date_dir = tmp_path / "2026" / "02" / "09"
        date_dir.mkdir(parents=True, exist_ok=True)
        filename = f"rollout-2026-02-09T10-00-{session_id}.jsonl"
        path = date_dir / filename

        events = [
            {
                "timestamp": "2026-02-09T10:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "cwd": cwd,
                    "timestamp": "2026-02-09T10:00:00.000Z",
                },
            }
        ]
        events.extend(messages)
        path.write_text("\n".join(json.dumps(e) for e in events))
        return path

    def _user_msg(self, text: str) -> dict:
        return {
            "timestamp": "2026-02-09T10:00:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }

    def _assistant_msg(self, text: str) -> dict:
        return {
            "timestamp": "2026-02-09T10:00:02.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        }

    @pytest.mark.asyncio
    async def test_list_sessions(self, tmp_path):
        """List sessions filtered by working directory."""
        store = self._make_store(tmp_path)
        sid = "019c4198-7cb8-7e23-9ae9-1265fc58404e"
        self._make_session_file(tmp_path, sid, "/home/user/project", [
            self._user_msg("Hello Codex"),
            self._assistant_msg("Hi there!"),
        ])
        # Different cwd — should not appear
        self._make_session_file(
            tmp_path, "019c4199-0000-0000-0000-000000000000",
            "/other/project", [self._user_msg("Other")]
        )

        result = await store.list_sessions("/home/user/project")
        assert len(result) == 1
        assert result[0].session_id == sid
        assert result[0].provider == "codex"
        assert result[0].title == "Hello Codex"

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, tmp_path):
        """No sessions directory → empty list."""
        store = self._make_store(tmp_path)
        result = await store.list_sessions("/tmp/test")
        assert result == []

    def test_find_session_file(self, tmp_path):
        """Find session file by ID in filename."""
        store = self._make_store(tmp_path)
        sid = "019c4198-7cb8-7e23-9ae9-1265fc58404e"
        created = self._make_session_file(tmp_path, sid, "/tmp/test", [])

        found = store._find_session_file(sid)
        assert found is not None
        assert found == created

    def test_find_session_file_not_found(self, tmp_path):
        """Non-existent session ID returns None."""
        store = self._make_store(tmp_path)
        found = store._find_session_file("nonexistent-id")
        assert found is None

    def test_load_messages_basic(self, tmp_path):
        """Load user and assistant messages from Codex session."""
        store = self._make_store(tmp_path)
        sid = "019c4198-7cb8-7e23-9ae9-1265fc58404e"
        self._make_session_file(tmp_path, sid, "/tmp/test", [
            self._user_msg("Ahoj, jaky jsi model?"),
            self._assistant_msg("Ahoj! Jsem ChatGPT, model GPT-5 od OpenAI."),
            self._user_msg("Diky, udelej neco"),
            self._assistant_msg("Jasne, tady je vysledek."),
        ])

        messages = store.load_session_messages(sid, "/tmp/test")
        assert len(messages) == 4
        assert messages[0].role == "user"
        assert messages[0].content == "Ahoj, jaky jsi model?"
        assert messages[1].role == "assistant"
        assert messages[1].content == "Ahoj! Jsem ChatGPT, model GPT-5 od OpenAI."
        assert messages[2].role == "user"
        assert messages[3].role == "assistant"

    def test_load_messages_not_found(self, tmp_path):
        """Non-existent session returns empty list."""
        store = self._make_store(tmp_path)
        messages = store.load_session_messages("nonexistent", "/tmp/test")
        assert messages == []

    def test_load_messages_skips_developer_and_reasoning(self, tmp_path):
        """Developer messages and reasoning should be skipped."""
        store = self._make_store(tmp_path)
        sid = "019c-skip-test"
        date_dir = tmp_path / "2026" / "02" / "09"
        date_dir.mkdir(parents=True, exist_ok=True)
        events = [
            {
                "type": "session_meta",
                "payload": {"id": sid, "cwd": "/tmp/test"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "<permissions>...</permissions>"}],
                },
            },
            {
                "type": "response_item",
                "payload": {"type": "reasoning", "role": "assistant"},
            },
            {
                "type": "event_msg",
                "payload": {"type": "info"},
            },
            self._user_msg("Real user question"),
            self._assistant_msg("Real answer"),
        ]
        (date_dir / f"rollout-2026-02-09T10-00-{sid}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages(sid, "/tmp/test")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "Real user question"
        assert messages[1].role == "assistant"

    def test_load_messages_skips_system_content(self, tmp_path):
        """User messages with system/instruction content should be filtered."""
        store = self._make_store(tmp_path)
        sid = "019c-sys-filter"
        date_dir = tmp_path / "2026" / "02" / "09"
        date_dir.mkdir(parents=True, exist_ok=True)
        events = [
            {
                "type": "session_meta",
                "payload": {"id": sid, "cwd": "/tmp/test"},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "# AGENTS.md instructions for /home/box"},
                    ],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "<environment_context>\n<cwd>/tmp</cwd>\n</environment_context>"},
                    ],
                },
            },
            self._user_msg("What is 2+2?"),
            self._assistant_msg("4"),
        ]
        (date_dir / f"rollout-2026-02-09T10-00-{sid}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events)
        )

        messages = store.load_session_messages(sid, "/tmp/test")
        assert len(messages) == 2
        assert messages[0].content == "What is 2+2?"
        assert messages[1].content == "4"
