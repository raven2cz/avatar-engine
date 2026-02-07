"""Avatar Engine CLI application."""

import os
from pathlib import Path

import click
from rich.console import Console

from .. import __version__

console = Console()


def find_config() -> str | None:
    """
    Find config file using standard priority order:

    1. AVATAR_CONFIG environment variable
    2. .avatar.yaml in current directory (project config)
    3. ~/.config/avatar-engine/config.yaml (user config)

    Returns None if no config found.
    """
    # 1. Environment variable (highest priority)
    env_config = os.environ.get("AVATAR_CONFIG")
    if env_config:
        path = Path(env_config)
        if path.exists():
            return str(path)

    # 2. Project config in current directory
    project_config = Path.cwd() / ".avatar.yaml"
    if project_config.exists():
        return str(project_config)

    # 3. User config in ~/.config/avatar-engine/
    user_config = Path.home() / ".config" / "avatar-engine" / "config.yaml"
    if user_config.exists():
        return str(user_config)

    return None


@click.group()
@click.version_option(version=__version__, prog_name="avatar")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--no-config", is_flag=True, help="Disable config auto-loading")
@click.option(
    "--provider", "-p",
    type=click.Choice(["gemini", "claude", "codex"]),
    default="gemini",
    help="AI provider",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--debug", is_flag=True, help="Debug mode")
@click.pass_context
def cli(ctx: click.Context, config: str, no_config: bool, provider: str, verbose: bool, debug: bool) -> None:
    """Avatar Engine — application-specific AI avatar runtime.

    Build and run configurable AI avatars inside your application.
    Your app controls behavior and context; CLI providers are runtime backends.

    Config file locations (in priority order):

        1. -c/--config PATH (explicit)

        2. AVATAR_CONFIG env var

        3. .avatar.yaml (project config)

        4. ~/.config/avatar-engine/config.yaml (user config)

    Examples:

        avatar chat "Hello, how are you?"

        avatar repl -p claude

        avatar health --check-cli
    """
    ctx.ensure_object(dict)

    # Determine config file
    if no_config:
        config = None
    elif config is None:
        config = find_config()
        if config and verbose:
            console.print(f"[dim]Using config: {config}[/dim]")

    ctx.obj["config"] = config
    ctx.obj["provider"] = provider
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug


# Import and register commands
from .commands import chat, repl, health, version, mcp

cli.add_command(chat.chat)
cli.add_command(repl.repl)
cli.add_command(health.health)
cli.add_command(version.version)
cli.add_command(mcp.mcp)
