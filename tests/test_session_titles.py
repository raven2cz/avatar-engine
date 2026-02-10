"""Tests for SessionTitleRegistry — custom session title persistence."""

import json
from pathlib import Path

import pytest

from avatar_engine.sessions._titles import SessionTitleRegistry


@pytest.fixture
def registry(tmp_path: Path) -> SessionTitleRegistry:
    return SessionTitleRegistry(path=tmp_path / "titles.json")


class TestSessionTitleRegistry:

    def test_get_returns_none_for_unknown(self, registry: SessionTitleRegistry):
        assert registry.get("nonexistent") is None

    def test_set_and_get(self, registry: SessionTitleRegistry):
        registry.set("sess-1", "My Title")
        assert registry.get("sess-1") == "My Title"

    def test_set_overwrites(self, registry: SessionTitleRegistry):
        registry.set("sess-1", "Old")
        registry.set("sess-1", "New")
        assert registry.get("sess-1") == "New"

    def test_delete(self, registry: SessionTitleRegistry):
        registry.set("sess-1", "Title")
        registry.delete("sess-1")
        assert registry.get("sess-1") is None

    def test_delete_nonexistent_is_noop(self, registry: SessionTitleRegistry):
        registry.delete("nonexistent")  # should not raise

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "titles.json"
        reg1 = SessionTitleRegistry(path=path)
        reg1.set("sess-1", "Persisted Title")

        # New instance loads from same file
        reg2 = SessionTitleRegistry(path=path)
        assert reg2.get("sess-1") == "Persisted Title"

    def test_file_format(self, registry: SessionTitleRegistry):
        registry.set("a", "Title A")
        registry.set("b", "Title B")
        data = json.loads(registry._path.read_text())
        assert data == {"a": "Title A", "b": "Title B"}

    def test_empty_file(self, tmp_path: Path):
        path = tmp_path / "titles.json"
        path.write_text("")
        reg = SessionTitleRegistry(path=path)
        assert reg.get("x") is None

    def test_corrupt_file(self, tmp_path: Path):
        path = tmp_path / "titles.json"
        path.write_text("{invalid json")
        reg = SessionTitleRegistry(path=path)
        assert reg.get("x") is None

    def test_nonexistent_file(self, tmp_path: Path):
        path = tmp_path / "subdir" / "titles.json"
        reg = SessionTitleRegistry(path=path)
        assert reg.get("x") is None
        # Setting creates the file and parent dirs
        reg.set("x", "val")
        assert path.exists()

    def test_unicode_titles(self, registry: SessionTitleRegistry):
        registry.set("sess-1", "Refaktoring auth modulu")
        assert registry.get("sess-1") == "Refaktoring auth modulu"
        registry.set("sess-2", "CSS tema upravy")
        assert registry.get("sess-2") == "CSS tema upravy"

    def test_non_dict_json_ignored(self, tmp_path: Path):
        """JSON file containing a list/string/number is treated as empty."""
        path = tmp_path / "titles.json"
        path.write_text('["not", "a", "dict"]')
        reg = SessionTitleRegistry(path=path)
        assert reg.get("x") is None

    def test_non_dict_json_number(self, tmp_path: Path):
        path = tmp_path / "titles.json"
        path.write_text("42")
        reg = SessionTitleRegistry(path=path)
        assert reg.get("x") is None
        # Can still set and save over the bad file
        reg.set("x", "works")
        assert reg.get("x") == "works"

    def test_delete_persists(self, tmp_path: Path):
        path = tmp_path / "titles.json"
        reg = SessionTitleRegistry(path=path)
        reg.set("a", "Title A")
        reg.set("b", "Title B")
        reg.delete("a")
        # Reload from file
        reg2 = SessionTitleRegistry(path=path)
        assert reg2.get("a") is None
        assert reg2.get("b") == "Title B"
