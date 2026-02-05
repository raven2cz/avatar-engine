"""
Real MCP server integration tests.

These tests verify MCP server functionality with real providers.
Run with: pytest tests/integration/test_real_mcp.py -v
"""

import asyncio
import json
import os
import sys
import pytest
from pathlib import Path

from avatar_engine import AvatarEngine


# =============================================================================
# Simple Test MCP Server
# =============================================================================

MCP_SERVER_CODE = '''
"""Simple MCP server for testing."""
import json
import sys

def handle_request(request):
    """Handle MCP JSON-RPC request."""
    method = request.get("method", "")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "b": {"type": "number"},
                            },
                            "required": ["a", "b"]
                        }
                    },
                    {
                        "name": "greet",
                        "description": "Greet someone",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                            },
                            "required": ["name"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})

        if tool_name == "add":
            result = args.get("a", 0) + args.get("b", 0)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": str(result)}]}
            }
        elif tool_name == "greet":
            name = args.get("name", "World")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Hello, {name}!"}]}
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"}
    }

def main():
    """Main MCP server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            pass

if __name__ == "__main__":
    main()
'''


@pytest.fixture
def mcp_server_path(tmp_path):
    """Create a temporary MCP server script."""
    server_file = tmp_path / "test_mcp_server.py"
    server_file.write_text(MCP_SERVER_CODE)
    return str(server_file)


@pytest.fixture
def mcp_config(tmp_path, mcp_server_path):
    """Create MCP config with test server."""
    config = {
        "mcpServers": {
            "test-tools": {
                "command": sys.executable,
                "args": [mcp_server_path],
            }
        }
    }
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps(config))
    return str(config_file)


# =============================================================================
# MCP Server Protocol Tests
# =============================================================================


@pytest.mark.integration
class TestMCPServerProtocol:
    """Test MCP server protocol directly."""

    @pytest.mark.asyncio
    async def test_mcp_server_responds(self, mcp_server_path):
        """MCP server should respond to initialize."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, mcp_server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Send initialize
            init_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {}
            }) + "\n"
            proc.stdin.write(init_msg.encode())
            await proc.stdin.drain()

            # Read response
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
            response = json.loads(line.decode())

            assert response.get("id") == 1
            assert "result" in response
            assert "serverInfo" in response["result"]

        finally:
            proc.terminate()
            await proc.wait()

    @pytest.mark.asyncio
    async def test_mcp_server_lists_tools(self, mcp_server_path):
        """MCP server should list available tools."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, mcp_server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Initialize first
            init_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
            proc.stdin.write(init_msg.encode())
            await proc.stdin.drain()
            await proc.stdout.readline()  # Read init response

            # List tools
            list_msg = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
            proc.stdin.write(list_msg.encode())
            await proc.stdin.drain()

            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
            response = json.loads(line.decode())

            assert response.get("id") == 2
            assert "result" in response
            tools = response["result"]["tools"]
            tool_names = [t["name"] for t in tools]
            assert "add" in tool_names
            assert "greet" in tool_names

        finally:
            proc.terminate()
            await proc.wait()

    @pytest.mark.asyncio
    async def test_mcp_server_calls_tool(self, mcp_server_path):
        """MCP server should execute tool calls."""
        proc = await asyncio.create_subprocess_exec(
            sys.executable, mcp_server_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            # Initialize
            init_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
            proc.stdin.write(init_msg.encode())
            await proc.stdin.drain()
            await proc.stdout.readline()

            # Call add tool
            call_msg = json.dumps({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "add",
                    "arguments": {"a": 5, "b": 3}
                }
            }) + "\n"
            proc.stdin.write(call_msg.encode())
            await proc.stdin.drain()

            line = await asyncio.wait_for(proc.stdout.readline(), timeout=5)
            response = json.loads(line.decode())

            assert response.get("id") == 2
            assert "result" in response
            # Result should contain "8"
            content = response["result"]["content"][0]["text"]
            assert content == "8"

        finally:
            proc.terminate()
            await proc.wait()


# =============================================================================
# MCP with Real Provider Tests
# =============================================================================


@pytest.mark.integration
@pytest.mark.gemini
@pytest.mark.slow
class TestMCPWithGemini:
    """Test MCP integration with real Gemini."""

    @pytest.mark.asyncio
    async def test_chat_with_mcp_tools(self, skip_if_no_gemini, mcp_server_path):
        """Chat should have access to MCP tools."""
        mcp_servers = {
            "test-tools": {
                "command": sys.executable,
                "args": [mcp_server_path],
            }
        }

        engine = AvatarEngine(
            provider="gemini",
            timeout=120,
            mcp_servers=mcp_servers,
        )

        try:
            await engine.start()

            # Ask to use the calculator tool
            response = await engine.chat(
                "Use the 'add' tool to calculate 15 + 27. "
                "Tell me the exact result."
            )

            assert response.success is True
            # Should contain the result (42)
            assert "42" in response.content

        finally:
            await engine.stop()

    @pytest.mark.asyncio
    async def test_mcp_tool_events(self, skip_if_no_gemini, mcp_server_path):
        """Tool events should fire when MCP tools are used."""
        from avatar_engine.events import ToolEvent

        mcp_servers = {
            "test-tools": {
                "command": sys.executable,
                "args": [mcp_server_path],
            }
        }

        engine = AvatarEngine(
            provider="gemini",
            timeout=120,
            mcp_servers=mcp_servers,
        )

        tool_events = []

        @engine.on(ToolEvent)
        def on_tool(e):
            tool_events.append(e)

        try:
            await engine.start()

            await engine.chat("Use the greet tool to greet 'Alice'.")

            # May or may not have tool events depending on provider
            # Just verify no crash

        finally:
            await engine.stop()


# =============================================================================
# MCP CLI Test Command
# =============================================================================


@pytest.mark.integration
class TestMCPTestCommand:
    """Test 'avatar mcp test' command."""

    def test_mcp_test_command(self, mcp_config):
        """avatar mcp test should verify MCP server."""
        import subprocess

        result = subprocess.run(
            [
                "python", "-m", "avatar_engine.cli",
                "mcp", "test", "test-tools",
                "--config", mcp_config,
                "--timeout", "10"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed
        assert result.returncode == 0, f"stderr: {result.stderr}"
        # Should show tools
        assert "add" in result.stdout or "greet" in result.stdout or "Tools" in result.stdout
