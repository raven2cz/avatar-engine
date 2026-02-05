"""MCP server management commands."""

import asyncio
import json
import os
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

import yaml

console = Console()


@click.group()
def mcp() -> None:
    """Manage MCP (Model Context Protocol) servers.

    Examples:

        avatar mcp list

        avatar mcp add mytools python mcp_server.py

        avatar mcp test mytools
    """
    pass


@mcp.command("list")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.pass_context
def mcp_list(ctx: click.Context, config: str) -> None:
    """List configured MCP servers."""
    config_path = config or ctx.obj.get("config")
    servers = _load_mcp_servers(config_path)

    if not servers:
        console.print("[dim]No MCP servers configured[/dim]")
        console.print("\n[dim]Add one with: avatar mcp add NAME COMMAND [ARGS...][/dim]")
        return

    table = Table(title="MCP Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Command")
    table.add_column("Args")
    table.add_column("Env")

    for name, srv in servers.items():
        args = " ".join(srv.get("args", []))
        env = ", ".join(f"{k}={v}" for k, v in srv.get("env", {}).items()) or "-"
        table.add_row(name, srv.get("command", ""), args, env[:30])

    console.print(table)


@mcp.command("add")
@click.argument("name")
@click.argument("command")
@click.argument("args", nargs=-1)
@click.option("--env", "-e", multiple=True, help="Environment var: KEY=VALUE")
@click.option("--config", "-c", type=click.Path(), default="mcp_servers.json", help="Config file")
def mcp_add(name: str, command: str, args: tuple, env: tuple, config: str) -> None:
    """Add an MCP server configuration.

    Examples:

        avatar mcp add calculator python calc_server.py

        avatar mcp add filetools python files.py --env DEBUG=1
    """
    config_path = Path(config)

    # Load existing or create new
    if config_path.exists():
        data = json.loads(config_path.read_text())
    else:
        data = {"mcpServers": {}}

    # Parse env vars
    env_dict = {}
    for e in env:
        if "=" in e:
            k, v = e.split("=", 1)
            env_dict[k] = v

    # Add server
    data["mcpServers"][name] = {
        "command": command,
        "args": list(args),
    }
    if env_dict:
        data["mcpServers"][name]["env"] = env_dict

    config_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]✓[/green] Added MCP server: [cyan]{name}[/cyan]")
    console.print(f"[dim]Config saved to: {config_path}[/dim]")


@mcp.command("remove")
@click.argument("name")
@click.option("--config", "-c", type=click.Path(exists=True), default="mcp_servers.json", help="Config file")
def mcp_remove(name: str, config: str) -> None:
    """Remove an MCP server configuration."""
    config_path = Path(config)

    if not config_path.exists():
        console.print(f"[red]Config file not found: {config}[/red]")
        raise SystemExit(1)

    data = json.loads(config_path.read_text())

    if name not in data.get("mcpServers", {}):
        console.print(f"[red]MCP server not found: {name}[/red]")
        raise SystemExit(1)

    del data["mcpServers"][name]
    config_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]✓[/green] Removed MCP server: [cyan]{name}[/cyan]")


@mcp.command("test")
@click.argument("name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.option("--timeout", "-t", default=10, help="Timeout in seconds")
@click.pass_context
def mcp_test(ctx: click.Context, name: str, config: str, timeout: int) -> None:
    """Test an MCP server by listing its tools.

    Starts the MCP server and sends a tools/list request.
    """
    config_path = config or ctx.obj.get("config") or "mcp_servers.json"
    servers = _load_mcp_servers(config_path)

    if name not in servers:
        console.print(f"[red]MCP server not found: {name}[/red]")
        console.print(f"[dim]Available: {', '.join(servers.keys()) if servers else 'none'}[/dim]")
        raise SystemExit(1)

    srv = servers[name]
    asyncio.run(_test_mcp_server(name, srv, timeout))


async def _test_mcp_server(name: str, srv: dict, timeout: int) -> None:
    """Test MCP server by requesting tools list."""
    cmd = [srv["command"]] + srv.get("args", [])
    console.print(f"[dim]Testing: {name}[/dim]")
    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **srv.get("env", {})},
        )

        # Send MCP initialize + tools/list
        init_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "avatar-cli", "version": "0.1.0"},
                "capabilities": {},
            }
        })
        tools_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        })

        proc.stdin.write(f"{init_msg}\n{tools_msg}\n".encode())
        await proc.stdin.drain()

        # Read responses
        tools = []
        try:
            async with asyncio.timeout(timeout):
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    try:
                        resp = json.loads(line.decode())
                        if resp.get("id") == 2 and "result" in resp:
                            tools = resp["result"].get("tools", [])
                            break
                    except json.JSONDecodeError:
                        continue
        except asyncio.TimeoutError:
            console.print("[yellow]Warning: Timeout waiting for response[/yellow]")

        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()

        if tools:
            table = Table(title=f"Tools from {name}")
            table.add_column("Name", style="cyan")
            table.add_column("Description")

            for tool in tools:
                desc = tool.get("description", "")
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                table.add_row(tool.get("name", "?"), desc)

            console.print(table)
            console.print(f"[green]✓[/green] Found {len(tools)} tools")
        else:
            console.print("[yellow]No tools found (server may not support tools/list)[/yellow]")

    except FileNotFoundError:
        console.print(f"[red]Command not found: {srv['command']}[/red]")
        raise SystemExit(1)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise SystemExit(1)


def _load_mcp_servers(config_path: str) -> dict:
    """Load MCP servers from config file."""
    if not config_path:
        # Try default locations
        for path in ["mcp_servers.json", "config.yaml", ".claude/settings.json", ".gemini/settings.json"]:
            if Path(path).exists():
                config_path = path
                break

    if not config_path or not Path(config_path).exists():
        return {}

    path = Path(config_path)
    content = path.read_text()

    if path.suffix == ".json":
        data = json.loads(content)
        return data.get("mcpServers", {})

    elif path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(content)
        # Check both gemini and claude config locations
        if "gemini" in data and "mcp_servers" in data["gemini"]:
            return data["gemini"]["mcp_servers"]
        if "claude" in data and "mcp_servers" in data["claude"]:
            return data["claude"]["mcp_servers"]
        return data.get("mcp_servers", {})

    return {}
