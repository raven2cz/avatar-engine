"""Version checking utilities for Avatar Engine."""

import asyncio
import logging
import shutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VersionInfo:
    """CLI version information."""
    executable: str
    version: Optional[str] = None
    available: bool = False
    error: Optional[str] = None


async def check_cli_version(executable: str, timeout: float = 10.0) -> VersionInfo:
    """
    Check the version of a CLI tool.

    Args:
        executable: Path or name of the executable
        timeout: Timeout in seconds

    Returns:
        VersionInfo with version string or error
    """
    # Check if executable exists
    path = shutil.which(executable)
    if not path:
        return VersionInfo(
            executable=executable,
            available=False,
            error=f"Executable not found: {executable}",
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            path, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode == 0:
            version = stdout.decode(errors="replace").strip()
            # Some CLIs output to stderr
            if not version:
                version = stderr.decode(errors="replace").strip()
            return VersionInfo(
                executable=executable,
                version=version or "unknown",
                available=True,
            )
        else:
            error = stderr.decode(errors="replace").strip() or "Unknown error"
            return VersionInfo(
                executable=executable,
                available=True,
                error=f"Version check failed: {error}",
            )

    except asyncio.TimeoutError:
        return VersionInfo(
            executable=executable,
            available=True,
            error=f"Version check timed out after {timeout}s",
        )
    except Exception as exc:
        return VersionInfo(
            executable=executable,
            available=False,
            error=str(exc),
        )


def check_cli_version_sync(executable: str, timeout: float = 10.0) -> VersionInfo:
    """Synchronous version of check_cli_version."""
    return asyncio.run(check_cli_version(executable, timeout))


async def check_all_cli_versions() -> dict[str, VersionInfo]:
    """Check versions of all supported CLIs."""
    executables = ["claude", "gemini"]
    tasks = [check_cli_version(exe) for exe in executables]
    results = await asyncio.gather(*tasks)
    return {exe: info for exe, info in zip(executables, results)}


def log_cli_versions() -> None:
    """Check and log CLI versions (synchronous)."""
    versions = asyncio.run(check_all_cli_versions())
    for exe, info in versions.items():
        if info.available:
            if info.version:
                logger.info(f"{exe}: {info.version}")
            else:
                logger.info(f"{exe}: available (version unknown)")
        else:
            logger.warning(f"{exe}: {info.error}")
