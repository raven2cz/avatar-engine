# Claude Code Headless Mode Documentation

> Source: https://code.claude.com/docs/en/headless

## Overview

Claude Code's headless mode (now called "Agent SDK CLI") enables programmatic execution via the `-p` flag. It provides the same tools, agent loop, and context management that power the interactive Claude Code.

## Basic Usage

```bash
claude -p "Find and fix the bug in auth.py" --allowedTools "Read,Edit,Bash"
```

## Output Formats

### Text Output (Default)

Plain text output without structured metadata:

```bash
claude -p "What does the auth module do?"
```

### JSON Output

Structured JSON with result, session ID, and metadata:

```bash
claude -p "Summarize this project" --output-format json
```

The text result is in the `result` field.

### Stream-JSON (Streaming Output)

Newline-delimited JSON for real-time streaming:

```bash
claude -p "Explain recursion" --output-format stream-json --verbose --include-partial-messages
```

**Event types:**
- `system` / `init` — Session initialization with session_id
- `user` — User message echo
- `assistant` — Assistant response with content blocks
- `tool_use` — Tool invocation
- `tool_result` — Tool execution result
- `stream_event` — Partial text deltas (with `--include-partial-messages`)
- `result` — Final result with usage stats

**Filter for streaming text:**
```bash
claude -p "Write a poem" --output-format stream-json --verbose --include-partial-messages | \
  jq -rj 'select(.type == "stream_event" and .event.delta.type? == "text_delta") | .event.delta.text'
```

### Structured Output with JSON Schema

```bash
claude -p "Extract the main function names from auth.py" \
  --output-format json \
  --json-schema '{"type":"object","properties":{"functions":{"type":"array","items":{"type":"string"}}},"required":["functions"]}'
```

## Key CLI Flags

| Flag | Description | Example |
|------|-------------|---------|
| `-p`, `--print` | Headless mode | `claude -p "query"` |
| `--output-format` | Output format (text, json, stream-json) | `--output-format stream-json` |
| `--input-format` | Input format (text, stream-json) | `--input-format stream-json` |
| `--model` | Model selection (sonnet, opus, haiku) | `--model opus` |
| `--allowedTools` | Auto-approved tools | `--allowedTools "Read,Edit,Bash"` |
| `--permission-mode` | Permission mode | `--permission-mode acceptEdits` |
| `--continue`, `-c` | Continue last conversation | `claude -c -p "query"` |
| `--resume`, `-r` | Resume specific session | `claude -r "session-id" "query"` |
| `--append-system-prompt` | Add to system prompt | `--append-system-prompt "Use TypeScript"` |
| `--mcp-config` | MCP server config file | `--mcp-config ./mcp.json` |
| `--verbose` | Include all event types | `--verbose` |
| `--include-partial-messages` | Stream text deltas | `--include-partial-messages` |
| `--max-turns` | Limit agentic turns | `--max-turns 3` |
| `--max-budget-usd` | Budget limit | `--max-budget-usd 5.00` |

## Stream-JSON Input Format

For persistent sessions, use `--input-format stream-json`:

```bash
claude -p --input-format stream-json --output-format stream-json
```

**Input message format:**
```json
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello!"}]}}
```

**With session_id for continuation:**
```json
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Continue..."}]},"session_id":"abc-123"}
```

## Permission Modes

| Mode | Description |
|------|-------------|
| `default` | Prompt for all tool uses |
| `acceptEdits` | Auto-approve file edits |
| `bypassPermissions` | Skip all prompts (dangerous) |
| `plan` | Planning mode, no execution |

## Tool Allowlist Patterns

```bash
# Specific tools
--allowedTools "Read,Edit,Bash"

# Git commands with prefix matching
--allowedTools "Bash(git diff *)" "Bash(git log *)" "Bash(git commit *)"

# MCP tools with wildcard
--allowedTools "mcp__avatar-tools__*"
```

## Session Management

**Continue most recent:**
```bash
claude -p "Continue the review" --continue
```

**Resume specific session:**
```bash
session_id=$(claude -p "Start a review" --output-format json | jq -r '.session_id')
claude -p "Continue that review" --resume "$session_id"
```

## MCP Configuration

**Via file:**
```bash
claude --mcp-config ./mcp_servers.json -p "Use tools"
```

**mcp_servers.json format:**
```json
{
  "mcpServers": {
    "avatar-tools": {
      "command": "python",
      "args": ["mcp_tools.py"]
    }
  }
}
```

## System Prompt Customization

| Flag | Behavior |
|------|----------|
| `--system-prompt` | Replace entire prompt |
| `--system-prompt-file` | Replace with file contents |
| `--append-system-prompt` | Append to default prompt |
| `--append-system-prompt-file` | Append file contents |

**Recommended:** Use `--append-system-prompt` to preserve Claude Code defaults.
