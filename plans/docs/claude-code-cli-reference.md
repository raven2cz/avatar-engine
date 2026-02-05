# Claude Code CLI Reference

> Source: https://code.claude.com/docs/en/cli-reference

## CLI Commands

| Command | Description | Example |
|---------|-------------|---------|
| `claude` | Start interactive REPL | `claude` |
| `claude "query"` | Start REPL with initial prompt | `claude "explain this project"` |
| `claude -p "query"` | Query via SDK, then exit | `claude -p "explain this function"` |
| `cat file \| claude -p "query"` | Process piped content | `cat logs.txt \| claude -p "explain"` |
| `claude -c` | Continue most recent conversation | `claude -c` |
| `claude -c -p "query"` | Continue via SDK | `claude -c -p "Check for type errors"` |
| `claude -r "<session>" "query"` | Resume session by ID or name | `claude -r "auth-refactor" "Finish this PR"` |
| `claude update` | Update to latest version | `claude update` |
| `claude mcp` | Configure MCP servers | See MCP documentation |

## Complete CLI Flags

| Flag | Description | Example |
|------|-------------|---------|
| `--add-dir` | Add additional working directories | `claude --add-dir ../apps ../lib` |
| `--agent` | Specify an agent for the session | `claude --agent my-custom-agent` |
| `--agents` | Define custom subagents via JSON | See below |
| `--allow-dangerously-skip-permissions` | Enable permission bypassing option | `claude --permission-mode plan --allow-dangerously-skip-permissions` |
| `--allowedTools` | Tools that execute without prompting | `"Bash(git log *)" "Read"` |
| `--append-system-prompt` | Append to default system prompt | `claude --append-system-prompt "Always use TypeScript"` |
| `--append-system-prompt-file` | Append from file (print mode only) | `claude -p --append-system-prompt-file ./extra-rules.txt "query"` |
| `--betas` | Beta headers for API (API key only) | `claude --betas interleaved-thinking` |
| `--chrome` | Enable Chrome browser integration | `claude --chrome` |
| `--continue`, `-c` | Load most recent conversation | `claude --continue` |
| `--dangerously-skip-permissions` | Skip all permission prompts | `claude --dangerously-skip-permissions` |
| `--debug` | Enable debug mode with category filtering | `claude --debug "api,mcp"` |
| `--disable-slash-commands` | Disable all skills/slash commands | `claude --disable-slash-commands` |
| `--disallowedTools` | Tools removed from context | `"Bash(git log *)" "Edit"` |
| `--fallback-model` | Fallback when default overloaded | `claude -p --fallback-model sonnet "query"` |
| `--fork-session` | Create new session ID when resuming | `claude --resume abc123 --fork-session` |
| `--from-pr` | Resume sessions linked to GitHub PR | `claude --from-pr 123` |
| `--ide` | Auto-connect to IDE on startup | `claude --ide` |
| `--init` | Run initialization hooks | `claude --init` |
| `--init-only` | Run init hooks and exit | `claude --init-only` |
| `--include-partial-messages` | Include partial streaming events | `claude -p --output-format stream-json --include-partial-messages "query"` |
| `--input-format` | Input format (text, stream-json) | `claude -p --input-format stream-json` |
| `--json-schema` | Get validated JSON output | `claude -p --json-schema '{...}' "query"` |
| `--maintenance` | Run maintenance hooks and exit | `claude --maintenance` |
| `--max-budget-usd` | Maximum dollar amount to spend | `claude -p --max-budget-usd 5.00 "query"` |
| `--max-turns` | Limit agentic turns (print mode) | `claude -p --max-turns 3 "query"` |
| `--mcp-config` | Load MCP servers from JSON | `claude --mcp-config ./mcp.json` |
| `--model` | Set model (sonnet, opus, or full name) | `claude --model claude-sonnet-4-5-20250929` |
| `--no-chrome` | Disable Chrome integration | `claude --no-chrome` |
| `--no-session-persistence` | Don't save sessions to disk | `claude -p --no-session-persistence "query"` |
| `--output-format` | Output format (text, json, stream-json) | `claude -p "query" --output-format json` |
| `--permission-mode` | Start in specified permission mode | `claude --permission-mode plan` |
| `--permission-prompt-tool` | MCP tool for permission prompts | `claude -p --permission-prompt-tool mcp_auth_tool "query"` |
| `--plugin-dir` | Load plugins from directories | `claude --plugin-dir ./my-plugins` |
| `--print`, `-p` | Print response, no interactive mode | `claude -p "query"` |
| `--remote` | Create web session on claude.ai | `claude --remote "Fix the login bug"` |
| `--resume`, `-r` | Resume session by ID or name | `claude --resume auth-refactor` |
| `--session-id` | Use specific session ID (UUID) | `claude --session-id "550e8400-..."` |
| `--setting-sources` | Setting sources to load | `claude --setting-sources user,project` |
| `--settings` | Path to settings JSON file | `claude --settings ./settings.json` |
| `--strict-mcp-config` | Only use MCP from --mcp-config | `claude --strict-mcp-config --mcp-config ./mcp.json` |
| `--system-prompt` | Replace entire system prompt | `claude --system-prompt "You are a Python expert"` |
| `--system-prompt-file` | Load system prompt from file | `claude -p --system-prompt-file ./prompt.txt "query"` |
| `--teleport` | Resume web session locally | `claude --teleport` |
| `--tools` | Restrict available tools | `claude --tools "Bash,Edit,Read"` |
| `--verbose` | Enable verbose logging | `claude --verbose` |
| `--version`, `-v` | Output version number | `claude -v` |

## Custom Subagents Format

The `--agents` flag accepts JSON:

```json
{
  "code-reviewer": {
    "description": "Expert code reviewer. Use proactively after code changes.",
    "prompt": "You are a senior code reviewer. Focus on code quality, security, and best practices.",
    "tools": ["Read", "Grep", "Glob", "Bash"],
    "model": "sonnet"
  },
  "debugger": {
    "description": "Debugging specialist for errors and test failures.",
    "prompt": "You are an expert debugger. Analyze errors, identify root causes, and provide fixes."
  }
}
```

**Fields:**
| Field | Required | Description |
|-------|----------|-------------|
| `description` | Yes | When the subagent should be invoked |
| `prompt` | Yes | System prompt for the subagent |
| `tools` | No | Array of tools (inherits all if omitted) |
| `model` | No | Model alias: `sonnet`, `opus`, `haiku`, `inherit` |

## System Prompt Flags Summary

| Flag | Behavior | Modes |
|------|----------|-------|
| `--system-prompt` | Replace entire prompt | Interactive + Print |
| `--system-prompt-file` | Replace with file | Print only |
| `--append-system-prompt` | Append to default | Interactive + Print |
| `--append-system-prompt-file` | Append file | Print only |

**Recommendation:** Use `--append-system-prompt` for most cases to preserve Claude Code defaults.

## Models

| Alias | Full Name | Notes |
|-------|-----------|-------|
| `opus` | `claude-opus-4-5` | Best quality, slower |
| `sonnet` | `claude-sonnet-4-5` | Fast, good for most use cases |
| `haiku` | `claude-haiku-3-5` | Fastest, lowest cost |
