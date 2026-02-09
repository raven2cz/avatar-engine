"""Tests for avatar_engine.web.uploads — UploadStorage."""

import time
from pathlib import Path

import pytest

from avatar_engine.web.uploads import UploadStorage, _sanitize_filename


class TestSanitizeFilename:
    def test_normal_filename(self):
        assert _sanitize_filename("photo.jpg") == "photo.jpg"

    def test_path_separators_removed(self):
        assert "/" not in _sanitize_filename("../../etc/passwd")
        assert "\\" not in _sanitize_filename("..\\..\\secret.txt")

    def test_null_bytes_removed(self):
        assert "\x00" not in _sanitize_filename("file\x00.txt")

    def test_unsafe_chars_replaced(self):
        result = _sanitize_filename("hello<world>.pdf")
        assert "<" not in result
        assert ">" not in result

    def test_max_length(self):
        long_name = "a" * 300 + ".pdf"
        assert len(_sanitize_filename(long_name, max_length=200)) <= 200

    def test_empty_string(self):
        assert _sanitize_filename("") == "unnamed"

    def test_only_dots(self):
        assert _sanitize_filename("...") == "unnamed"


class TestUploadStorage:
    def test_save_and_read(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        data = b"hello world"
        att = storage.save("test.txt", data, "text/plain")

        assert att.path.exists()
        assert att.path.read_bytes() == data
        assert att.filename == "test.txt"
        assert att.mime_type == "text/plain"
        assert att.size == len(data)

    def test_unique_filenames(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        a1 = storage.save("file.txt", b"one", "text/plain")
        a2 = storage.save("file.txt", b"two", "text/plain")
        assert a1.path != a2.path

    def test_max_size_enforcement(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        storage._max_bytes = 100
        with pytest.raises(ValueError, match="too large"):
            storage.save("big.bin", b"x" * 200, "application/octet-stream")

    def test_is_valid_path(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        att = storage.save("ok.txt", b"ok", "text/plain")
        assert storage.is_valid_path(att.path)
        assert not storage.is_valid_path(tmp_path / "other" / "evil.txt")
        assert not storage.is_valid_path(Path("/etc/passwd"))

    def test_cleanup_old(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        att = storage.save("old.txt", b"old", "text/plain")
        # Set mtime to 48 hours ago
        old_time = time.time() - 48 * 3600
        import os
        os.utime(att.path, (old_time, old_time))

        new_att = storage.save("new.txt", b"new", "text/plain")

        deleted = storage.cleanup_old(max_age_hours=24)
        assert deleted == 1
        assert not att.path.exists()
        assert new_att.path.exists()

    def test_base_dir_created(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "uploads"
        assert not target.exists()
        storage = UploadStorage(base_dir=target)
        assert target.is_dir()
        assert storage.base_dir == target

    def test_attachment_has_correct_fields(self, tmp_path):
        storage = UploadStorage(base_dir=tmp_path / "uploads")
        data = b"\x89PNG\r\n" + b"\x00" * 100
        att = storage.save("screenshot.png", data, "image/png")

        assert att.filename == "screenshot.png"
        assert att.mime_type == "image/png"
        assert att.size == len(data)
        assert att.path.parent == storage.base_dir
