"""
Upload storage for media file attachments.

Saves uploaded files to a local directory (default: system temp).
Provides Attachment objects for use with bridges.
"""

import logging
import os
import re
import tempfile
import time
from pathlib import Path
from uuid import uuid4
from typing import Optional

from ..types import Attachment

logger = logging.getLogger(__name__)

# Max upload size default: 100 MB (overridable via AVATAR_MAX_UPLOAD_MB env var)
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024

_UNSAFE_FILENAME_RE = re.compile(r'[^\w\-. ]')


def _sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a filename for safe disk storage."""
    # Strip path separators and null bytes
    name = name.replace("\x00", "").replace("/", "_").replace("\\", "_")
    # Remove unsafe characters
    name = _UNSAFE_FILENAME_RE.sub("_", name)
    # Collapse multiple underscores
    name = re.sub(r'_+', '_', name).strip("_. ")
    return name[:max_length] if name else "unnamed"


class UploadStorage:
    """Manages uploaded file storage on disk."""

    def __init__(self, base_dir: Optional[Path] = None):
        env_dir = os.environ.get("AVATAR_UPLOAD_DIR")
        if base_dir:
            self._base = base_dir
        elif env_dir:
            self._base = Path(env_dir)
        else:
            self._base = Path(tempfile.gettempdir()) / "avatar-engine" / "uploads"
        self._base.mkdir(parents=True, exist_ok=True)
        self._max_bytes = int(os.environ.get("AVATAR_MAX_UPLOAD_MB", "100")) * 1024 * 1024

    @property
    def base_dir(self) -> Path:
        return self._base

    @property
    def max_upload_bytes(self) -> int:
        return self._max_bytes

    def save(self, filename: str, data: bytes, mime_type: str) -> Attachment:
        """Save file data to disk and return an Attachment.

        Raises ValueError if file exceeds max upload size.
        """
        if len(data) > self._max_bytes:
            max_mb = self._max_bytes / (1024 * 1024)
            raise ValueError(f"File too large: {len(data)} bytes (max {max_mb:.0f} MB)")

        safe_name = f"{uuid4().hex[:12]}_{_sanitize_filename(filename)}"
        path = self._base / safe_name
        path.write_bytes(data)
        logger.info(f"Saved upload: {safe_name} ({len(data)} bytes, {mime_type})")
        return Attachment(path=path, mime_type=mime_type, filename=filename, size=len(data))

    def is_valid_path(self, path: Path) -> bool:
        """Check that a path is inside the upload directory (prevent traversal)."""
        try:
            path.resolve().relative_to(self._base.resolve())
            return True
        except ValueError:
            return False

    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Delete files older than max_age_hours. Returns count of deleted files."""
        if not self._base.is_dir():
            return 0
        cutoff = time.time() - (max_age_hours * 3600)
        deleted = 0
        for f in self._base.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        if deleted:
            logger.info(f"Cleaned up {deleted} old upload(s)")
        return deleted
