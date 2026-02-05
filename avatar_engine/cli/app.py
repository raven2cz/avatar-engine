"""Avatar Engine CLI application."""

import click
from rich.console import Console

from .. import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="avatar")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option(
    "--provider", "-p",
    type=click.Choice(["gemini", "claude"]),
    default="gemini",
    help="AI provider",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--debug", is_flag=True, help="Debug mode")
@click.pass_context
def cli(ctx: click.Context, config: str, provider: str, verbose: bool, debug: bool) -> None:
    """Avatar Engine — AI CLI Bridge.

    A unified interface for Claude Code and Gemini CLI.

    Examples:

        avatar chat "Hello, how are you?"

        avatar repl -p claude

        avatar health --check-cli
    """
    ctx.ensure_object(dict)
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
