# Avatar Engine Documentation Index

This directory contains reference documentation for building and maintaining the Avatar Engine.

## Documentation Files

### Gemini CLI

| File | Description |
|------|-------------|
| [gemini-cli-configuration.md](./gemini-cli-configuration.md) | Complete settings.json reference including model config, thinking, temperature |
| [gemini-cli-headless.md](./gemini-cli-headless.md) | Headless mode, output formats, stream-json |
| [gemini-3-developer-guide.md](./gemini-3-developer-guide.md) | Gemini 3 model capabilities, thinking levels, API parameters |
| [gemini-acp-issues-and-fixes.md](./gemini-acp-issues-and-fixes.md) | Known issues, workarounds, PR #9410 OAuth fix |

### Claude Code

| File | Description |
|------|-------------|
| [claude-code-headless.md](./claude-code-headless.md) | Headless mode, stream-json input/output, session management |
| [claude-code-cli-reference.md](./claude-code-cli-reference.md) | Complete CLI flags reference, permission modes, MCP config |

### ACP (Agent Client Protocol)

| File | Description |
|------|-------------|
| [acp-python-sdk.md](./acp-python-sdk.md) | Python SDK usage, schemas, streaming, known issues |

## Quick Reference

### Gemini CLI Warm Session

```bash
gemini --experimental-acp --yolo --model gemini-3-pro-preview
```

### Claude Code Warm Session

```bash
claude -p --input-format stream-json --output-format stream-json --verbose
```

### Key Configuration Files

| Provider | File | Purpose |
|----------|------|---------|
| Gemini | `.gemini/settings.json` | Model config, MCP servers, thinking |
| Claude | `.claude/settings.json` | Permissions, MCP servers |
| Claude | `mcp_servers.json` | MCP config for `--mcp-config` |
| Claude | `CLAUDE.md` | System prompt |
| Gemini | `GEMINI.md` | System prompt |

### Model Selection

| Provider | Model | Use Case |
|----------|-------|----------|
| Gemini | `gemini-3-pro-preview` | Best MCP support, latest reasoning |
| Gemini | `gemini-2.5-pro` | Stable, may have MCP issues |
| Claude | `claude-opus-4-5` | Best quality, slower |
| Claude | `claude-sonnet-4-5` | Fast, good for most use cases |
| Claude | `claude-haiku-3-5` | Fastest, lowest cost |

### Thinking Configuration (Gemini 3)

| Level | Latency | Use Case |
|-------|---------|----------|
| `minimal` | Lowest | Simple queries (cannot fully disable Pro) |
| `low` | Low | Straightforward tasks |
| `medium` | Medium | Balanced (Flash only) |
| `high` | Highest | Complex reasoning (default) |

## Sources

- Gemini CLI: https://github.com/google-gemini/gemini-cli
- Claude Code: https://code.claude.com/docs
- ACP SDK: https://agentclientprotocol.github.io/python-sdk/
- Gemini API: https://ai.google.dev/gemini-api/docs
