# Avatar Engine CLI — Implementation Plan

> Created: 2026-02-05
> Status: DONE (2026-02-08)
> Priority: MEDIUM (D1)

---

## 1. Účel CLI

CLI je **sekundární** — primární je library API. CLI slouží pro:
- **Development/Testing** — rychlé testování bridgů bez psaní kódu
- **Debugging** — sledování eventů, stderr, health checks
- **Demo** — ukázka capabilities pro nové uživatele
- **Scripting** — jednorázové dotazy z shell scriptů

---

## 2. Návrh CLI Interface

### 2.1 Základní příkazy

```bash
# Jednorázový dotaz (oneshot)
avatar chat "What is 2+2?"
avatar chat -p gemini "Explain quantum computing"
avatar chat -p claude --model claude-sonnet-4-5 "Write a haiku"

# Interaktivní režim (REPL)
avatar repl
avatar repl -p gemini
avatar --config custom.yaml repl

# Health check
avatar health
avatar health -p claude

# Version info
avatar version
avatar version --check-cli  # Zkontroluje claude/gemini CLI verze

# MCP Server management
avatar mcp list                           # Seznam nakonfigurovaných MCP serverů
avatar mcp add mytools "python mcp_server.py"  # Přidá MCP server
avatar mcp remove mytools                 # Odebere MCP server
avatar mcp test mytools                   # Otestuje MCP server (list tools)
```

### 2.2 Globální flagy

```bash
--provider, -p     # gemini | claude (default: gemini)
--model, -m        # Model name
--config, -c       # Path to YAML config file
--working-dir, -w  # Working directory
--timeout, -t      # Request timeout in seconds
--verbose, -v      # Verbose output (show events)
--debug            # Debug mode (show all internal state)
--json             # JSON output format

# MCP Server flagy
--mcp, -M          # MCP server config file (JSON)
--mcp-server       # Inline MCP server: "name:command arg1 arg2"
                   # Lze použít vícekrát pro více serverů
```

### 2.3 Chat-specific flagy

```bash
# Gemini specific
--thinking-level   # minimal | low | medium | high
--yolo             # Auto-approve all tool calls

# Claude specific
--permission-mode  # acceptEdits | plan | etc.
--max-turns        # Cost control
--allowed-tools    # Comma-separated tool list
```

---

## 3. Architektura

```
avatar_engine/
├── cli/
│   ├── __init__.py
│   ├── __main__.py      # Entry point: python -m avatar_engine.cli
│   ├── app.py           # Main CLI application
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── chat.py      # avatar chat
│   │   ├── repl.py      # avatar repl
│   │   ├── health.py    # avatar health
│   │   ├── version.py   # avatar version
│   │   └── mcp.py       # avatar mcp (list/add/remove/test)
│   └── utils/
│       ├── __init__.py
│       ├── output.py    # Formatting, colors
│       ├── config.py    # CLI config handling
│       └── mcp.py       # MCP server utilities
```

---

## 4. Dependencies

```toml
# pyproject.toml [project.optional-dependencies]
cli = [
    "rich>=13.0",      # Pretty terminal output, tables, progress
    "click>=8.0",      # CLI framework (nebo typer)
]
```

**Alternativy:**
- `click` — mature, explicit, wide adoption
- `typer` — modern, type hints, built on click
- `argparse` — stdlib, no deps, but verbose

**Doporučení:** `click` + `rich` pro balance mezi features a simplicity.

---

## 5. Implementační detaily

### 5.1 Entry Point (`__main__.py`)

```python
"""CLI entry point."""
from .app import cli

if __name__ == "__main__":
    cli()
```

### 5.2 Main App (`app.py`)

```python
"""Avatar Engine CLI."""
import click
from rich.console import Console

console = Console()

@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.option("--provider", "-p", type=click.Choice(["gemini", "claude"]), default="gemini")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.pass_context
def cli(ctx, config, provider, verbose):
    """Avatar Engine — AI CLI Bridge."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["provider"] = provider
    ctx.obj["verbose"] = verbose

# Import commands
from .commands import chat, repl, health, version
cli.add_command(chat.chat)
cli.add_command(repl.repl)
cli.add_command(health.health)
cli.add_command(version.version)
```

### 5.3 Chat Command (`commands/chat.py`)

```python
"""Chat command — single message interaction."""
import asyncio
import click
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from avatar_engine import AvatarEngine, TextEvent

console = Console()

@click.command()
@click.argument("message")
@click.option("--model", "-m", help="Model name")
@click.option("--stream/--no-stream", default=True, help="Stream output")
@click.option("--json", "json_output", is_flag=True, help="JSON output")
@click.pass_context
def chat(ctx, message, model, stream, json_output):
    """Send a message and get a response."""
    provider = ctx.obj["provider"]
    config_path = ctx.obj.get("config")
    verbose = ctx.obj.get("verbose", False)

    asyncio.run(_chat_async(
        message, provider, model, config_path,
        stream, json_output, verbose
    ))

async def _chat_async(message, provider, model, config_path, stream, json_output, verbose):
    # Create engine
    if config_path:
        engine = AvatarEngine.from_config(config_path)
    else:
        engine = AvatarEngine(provider=provider, model=model)

    # Verbose: show events
    if verbose:
        @engine.on(TextEvent)
        def on_text(event):
            console.print(f"[dim]TEXT:[/dim] {event.text[:50]}...")

    try:
        await engine.start()

        if stream:
            # Streaming output
            full_response = ""
            async for chunk in engine.chat_stream(message):
                console.print(chunk, end="")
                full_response += chunk
            console.print()  # Final newline
        else:
            # Complete response
            response = await engine.chat(message)
            if json_output:
                import json
                console.print_json(json.dumps({
                    "content": response.content,
                    "success": response.success,
                    "duration_ms": response.duration_ms,
                    "session_id": response.session_id,
                }))
            else:
                console.print(Markdown(response.content))

    finally:
        await engine.stop()
```

### 5.4 REPL Command (`commands/repl.py`)

```python
"""REPL command — interactive chat session."""
import asyncio
import click
from rich.console import Console
from rich.prompt import Prompt
from rich.markdown import Markdown

from avatar_engine import AvatarEngine, TextEvent, ToolEvent

console = Console()

@click.command()
@click.option("--model", "-m", help="Model name")
@click.pass_context
def repl(ctx, model):
    """Start interactive chat session."""
    provider = ctx.obj["provider"]
    config_path = ctx.obj.get("config")

    asyncio.run(_repl_async(provider, model, config_path))

async def _repl_async(provider, model, config_path):
    # Create engine
    if config_path:
        engine = AvatarEngine.from_config(config_path)
    else:
        engine = AvatarEngine(provider=provider, model=model)

    # Event handlers
    @engine.on(ToolEvent)
    def on_tool(event):
        if event.status == "started":
            console.print(f"[yellow]⚙ {event.tool_name}[/yellow]")

    console.print(f"[bold]Avatar Engine REPL[/bold] ({provider})")
    console.print("Type 'exit' or Ctrl+C to quit, '/clear' to reset history\n")

    try:
        await engine.start()

        while True:
            try:
                user_input = Prompt.ask("[bold blue]You[/bold blue]")

                if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                    break
                if user_input.lower() in ("/clear", "/reset"):
                    engine.clear_history()
                    console.print("[dim]History cleared[/dim]")
                    continue
                if user_input.lower() == "/health":
                    health = engine.get_health()
                    console.print_json(data=health.__dict__)
                    continue
                if user_input.lower() == "/stats":
                    stats = engine._bridge.get_stats() if engine._bridge else {}
                    console.print_json(data=stats)
                    continue
                if not user_input.strip():
                    continue

                console.print("[bold green]Assistant[/bold green]:")
                async for chunk in engine.chat_stream(user_input):
                    console.print(chunk, end="")
                console.print("\n")

            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit[/dim]")
                continue

    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()
        console.print("\n[dim]Session ended[/dim]")
```

### 5.5 Health Command (`commands/health.py`)

```python
"""Health check command."""
import asyncio
import click
from rich.console import Console
from rich.table import Table

from avatar_engine import AvatarEngine
from avatar_engine.utils import check_all_cli_versions

console = Console()

@click.command()
@click.option("--check-cli", is_flag=True, help="Check CLI tool versions")
@click.pass_context
def health(ctx, check_cli):
    """Check system health and CLI availability."""
    if check_cli:
        asyncio.run(_check_cli_versions())
    else:
        asyncio.run(_check_bridge_health(ctx.obj["provider"]))

async def _check_cli_versions():
    versions = await check_all_cli_versions()

    table = Table(title="CLI Tools")
    table.add_column("Tool", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Version/Error")

    for tool, info in versions.items():
        status = "✓" if info.available else "✗"
        detail = info.version if info.version else (info.error or "unknown")
        table.add_row(tool, status, detail)

    console.print(table)

async def _check_bridge_health(provider):
    engine = AvatarEngine(provider=provider)

    try:
        await engine.start()
        health = engine.get_health()

        table = Table(title=f"Bridge Health ({provider})")
        table.add_column("Metric", style="cyan")
        table.add_column("Value")

        for key, value in health.__dict__.items():
            table.add_row(key, str(value))

        console.print(table)
    finally:
        await engine.stop()
```

### 5.6 MCP Command (`commands/mcp.py`)

```python
"""MCP server management commands."""
import asyncio
import json
import os
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

@click.group()
def mcp():
    """Manage MCP (Model Context Protocol) servers."""
    pass

@mcp.command("list")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.pass_context
def mcp_list(ctx, config):
    """List configured MCP servers."""
    config_path = config or ctx.obj.get("config")
    servers = _load_mcp_servers(config_path)

    if not servers:
        console.print("[dim]No MCP servers configured[/dim]")
        return

    table = Table(title="MCP Servers")
    table.add_column("Name", style="cyan")
    table.add_column("Command")
    table.add_column("Args")

    for name, srv in servers.items():
        table.add_row(name, srv.get("command", ""), " ".join(srv.get("args", [])))

    console.print(table)

@mcp.command("add")
@click.argument("name")
@click.argument("command")
@click.argument("args", nargs=-1)
@click.option("--env", "-e", multiple=True, help="Environment var: KEY=VALUE")
@click.option("--config", "-c", type=click.Path(), help="Config file to update")
def mcp_add(name, command, args, env, config):
    """Add an MCP server configuration.

    Example: avatar mcp add mytools python mcp_server.py --arg1
    """
    config_path = Path(config) if config else Path("mcp_servers.json")

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
    console.print(f"[green]✓[/green] Added MCP server: {name}")

@mcp.command("remove")
@click.argument("name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
def mcp_remove(name, config):
    """Remove an MCP server configuration."""
    config_path = Path(config) if config else Path("mcp_servers.json")

    if not config_path.exists():
        console.print("[red]Config file not found[/red]")
        return

    data = json.loads(config_path.read_text())

    if name not in data.get("mcpServers", {}):
        console.print(f"[red]MCP server not found: {name}[/red]")
        return

    del data["mcpServers"][name]
    config_path.write_text(json.dumps(data, indent=2))
    console.print(f"[green]✓[/green] Removed MCP server: {name}")

@mcp.command("test")
@click.argument("name")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file")
@click.option("--timeout", "-t", default=10, help="Timeout in seconds")
def mcp_test(name, config, timeout):
    """Test an MCP server by listing its tools.

    Starts the MCP server and sends tools/list request.
    """
    config_path = Path(config) if config else Path("mcp_servers.json")
    servers = _load_mcp_servers(config_path)

    if name not in servers:
        console.print(f"[red]MCP server not found: {name}[/red]")
        return

    srv = servers[name]
    asyncio.run(_test_mcp_server(srv, timeout))

async def _test_mcp_server(srv: dict, timeout: int):
    """Test MCP server by requesting tools list."""
    import json

    cmd = [srv["command"]] + srv.get("args", [])
    console.print(f"[dim]Starting: {' '.join(cmd)}[/dim]")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **srv.get("env", {})},
        )

        # Send MCP initialize + tools/list
        init_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05",
                                         "clientInfo": {"name": "avatar-cli", "version": "0.1.0"}}})
        tools_msg = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

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

        if tools:
            table = Table(title=f"Tools from {srv['command']}")
            table.add_column("Name", style="cyan")
            table.add_column("Description")

            for tool in tools:
                table.add_row(tool.get("name", "?"), tool.get("description", "")[:60])

            console.print(table)
            console.print(f"[green]✓[/green] Found {len(tools)} tools")
        else:
            console.print("[yellow]No tools found (server may not support tools/list)[/yellow]")

    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")

def _load_mcp_servers(config_path) -> dict:
    """Load MCP servers from config file."""
    import yaml

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
```

### 5.7 MCP s chat/repl — příklady použití

```bash
# Chat s MCP serverem (inline)
avatar chat --mcp-server "tools:python mcp_tools.py" "Use the calculator tool to compute 15*7"

# Chat s MCP config souborem
avatar chat --mcp mcp_servers.json "List available files"

# REPL s MCP servery
avatar repl --mcp mcp_servers.json
avatar repl --mcp-server "calc:python calc_server.py" --mcp-server "files:python files_server.py"

# Kombinace s config.yaml (MCP servery z configu)
avatar repl --config config.yaml  # MCP servery se načtou z configu
```

### 5.8 REPL MCP příkazy

V REPL session jsou dostupné speciální příkazy pro MCP:

```
You> /tools              # Seznam všech dostupných MCP tools
You> /tool calc.add      # Detail konkrétního toolu
You> /mcp                # Status MCP serverů
```

---

## 6. Output Formatting

### 6.1 Rich komponenty

```python
# Streaming s Live display
from rich.live import Live
from rich.text import Text

with Live(Text(""), refresh_per_second=10) as live:
    async for chunk in engine.chat_stream(message):
        live.update(Text(full_text + chunk))
        full_text += chunk

# Markdown rendering
from rich.markdown import Markdown
console.print(Markdown(response.content))

# Tables pro health/stats
from rich.table import Table
table = Table(title="Stats")
table.add_column("Metric")
table.add_column("Value")

# Progress pro long operations
from rich.progress import Progress
with Progress() as progress:
    task = progress.add_task("Processing...", total=None)
    # ...
```

### 6.2 JSON output mode

```python
# Pro scripting/piping
if json_output:
    import json
    result = {
        "content": response.content,
        "success": response.success,
        "duration_ms": response.duration_ms,
        "tool_calls": response.tool_calls,
    }
    print(json.dumps(result, indent=2))
```

---

## 7. Implementační kroky

| Step | Task | Effort |
|------|------|--------|
| 1 | Vytvořit `cli/` strukturu | 5 min |
| 2 | Přidat `click` + `rich` do deps | 2 min |
| 3 | Implementovat `app.py` + entry point | 10 min |
| 4 | Implementovat `chat` command (+ MCP flags) | 25 min |
| 5 | Implementovat `repl` command (+ MCP commands) | 30 min |
| 6 | Implementovat `health` command | 10 min |
| 7 | Implementovat `version` command | 5 min |
| 8 | Implementovat `mcp` command group | 25 min |
| 9 | Testovat všechny commands | 20 min |
| 10 | Přidat do pyproject.toml scripts | 5 min |

**Celkem: ~2.5h**

---

## 8. pyproject.toml updates

```toml
[project.optional-dependencies]
cli = [
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
avatar = "avatar_engine.cli:cli"
```

---

## 9. Příklady použití

```bash
# Quick chat
avatar chat "Hello, how are you?"

# Claude s konkrétním modelem
avatar chat -p claude -m claude-sonnet-4-5 "Explain recursion"

# Gemini s thinking
avatar chat -p gemini --thinking-level high "Solve this math problem..."

# JSON output pro scripting
avatar chat --json "What is Python?" | jq .content

# REPL session
avatar repl -p gemini

# Health check
avatar health --check-cli

# S custom config
avatar -c myconfig.yaml repl

# === MCP Server Examples ===

# Přidat MCP server
avatar mcp add calculator python tools/calc_server.py
avatar mcp add filetools python tools/file_server.py --env "DEBUG=1"

# Seznam MCP serverů
avatar mcp list

# Otestovat MCP server (vypíše dostupné tools)
avatar mcp test calculator

# Chat s MCP serverem
avatar chat --mcp mcp_servers.json "Use calculator to compute 125 * 48"

# REPL s inline MCP serverem
avatar repl --mcp-server "calc:python tools/calc_server.py"

# REPL s více MCP servery
avatar repl --mcp-server "calc:python calc.py" --mcp-server "files:python files.py"

# V REPL session:
#   /tools           - seznam všech MCP tools
#   /tool calc.add   - detail konkrétního toolu
#   /mcp             - status MCP serverů
```

---

## 10. Implementation Status

Core CLI je implementované (chat, repl, health, version, mcp, session).
Zbývají drobné doplňky:

### 10.1 Chybějící flagy

| # | Flag | Soubor | Popis | Effort |
|---|------|--------|-------|--------|
| F1 | `--working-dir, -w` | `app.py` | Globální flag pro working directory, propaguje do engine | 5 min |
| F2 | `--allowed-tools` | `chat.py` | Comma-separated list allowed tools (Claude) | 5 min |

### 10.2 Chybějící REPL příkazy

| # | Příkaz | Soubor | Popis | Effort |
|---|--------|--------|-------|--------|
| R1 | `/tools` | `repl.py` | Vypíše seznam MCP tools z engine — volá bridge `list_tools()` nebo parsuje z MCP config | 15 min |
| R2 | `/tool <name>` | `repl.py` | Detail konkrétního MCP toolu (name, description, input schema) | 10 min |
| R3 | `/mcp` | `repl.py` | Status MCP serverů (nakonfigurované, aktivní) | 10 min |
| R4 | `/usage` | `repl.py` | Zobrazí usage statistiky aktuální session | 15 min |

### 10.3 `/usage` — detailní specifikace

Příkaz `/usage` zobrazí aktuální spotřebu session ve formátu Rich tabulky.

**Zdroj dat:** `BaseBridge._stats` (už sleduje requesty, duration, cost, tokeny) + provider-specific metody.

```
/usage
┌─────────────────────────────────┐
│ Session Usage (claude)          │
├─────────────────┬───────────────┤
│ Session ID      │ abc123...     │
│ Requests        │ 42 (40 ok)   │
│ Input tokens    │ 15,234        │
│ Output tokens   │ 8,942         │
│ Total cost      │ $0.47         │
│ Budget remaining│ $4.53 / $5.00 │
│ Avg latency     │ 1,234 ms      │
│ Uptime          │ 12m 34s       │
└─────────────────┴───────────────┘
```

**Dostupnost dat per provider:**

| Data | Claude | Gemini | Codex |
|------|--------|--------|-------|
| Request count | ✅ | ✅ | ✅ |
| Success rate | ✅ | ✅ | ✅ |
| Input/Output tokens | ✅ | ⚠️ partial | ⚠️ partial |
| Cost (USD) | ✅ | N/A (subscription) | N/A |
| Budget tracking | ✅ | N/A | N/A |
| Avg latency | ✅ | ✅ | ✅ |
| Uptime | ✅ | ✅ | ✅ |

Kde data nejsou dostupná, zobrazí se "—".

**Implementace:**
1. V `BaseBridge` přidat `get_usage() -> dict` — vrátí `_stats` + `uptime` + `session_id`
2. V `ClaudeBridge` override — přidat `cost`, `budget`, token breakdown
3. V `repl.py` — formátování přes Rich Table

**Celkem: ~55 min**
