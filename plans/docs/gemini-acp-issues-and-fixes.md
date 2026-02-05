# Gemini CLI ACP Issues and Fixes

> Source: https://github.com/google-gemini/gemini-cli/issues?q=ACP

## Critical Fix: PR #9410 — OAuth Credential Cache

**Issue #7549:** "ACP authentication doesn't use cached credentials"

### Problem

The system unconditionally cleared all cached authentication credentials on every `authenticate()` call, causing:

- **OAuth users:** Forced browser redirects on every new session
- **API Key users:** Unnecessary credential re-reads
- **Vertex AI users:** Unnecessary configuration reloads

### Solution

Introduced conditional credential clearing logic:
1. Check the current authentication type before clearing
2. Preserve credentials when re-authenticating with the same method
3. Only clear cache during actual auth method transitions

**Merged:** December 4, 2025
**Required version:** Gemini CLI >= v0.23.0

---

## Open Issues

### #18355 — `--experimental-acp` not working in newest version
- Command stops with no response
- Status: needs triage, possible duplicate

### #18084 — Add support for `set_model` in ACP
- Feature request for model switching capability

### #18076 — Gemini ACP `write_file` Tool Failure
- Tool execution problems in ACP mode

### #17952 — ACP mode tool confirmations delayed by ~30s
- Root cause: MessageBus timeout issue
- Priority: P1, help wanted

### #17854 — v26.0 ACP lacks MCP server tools
- Missing tool support in version 26.0

### #17588 — ACP fs delegation: map RESOURCE_NOT_FOUND to ENOENT
- File system error handling issue

### #17450 — Add rawInput + rawOutput to ACP
- Feature request for raw I/O support

### #16600 — ReadFolder tool doesn't display files
- File listing functionality issue

### #16504 — Support Custom API Endpoint and Key in ACP Mode
- Feature request for custom configuration

### #15502 — Load pre session not work on ACP mode with --resume
- Session resumption feature request

### #15338 — Add stateful headless mode (daemon/server mode)
- Persistent server capability request

---

## Closed/Fixed Issues

### #16620 — Add `communicate` tool kind
- Completed: Jan 22, 2026

### #14893 — Exhausted daily quota error
- Completed: Feb 3, 2026

### #13913 — ACP subprocess mode broken in v0.18.0+
- Completed: Dec 2, 2025
- This was the OAuth credential issue fixed by PR #9410

### #13641 — Not following ACP protocol definition
- Completed: Dec 1, 2025

### #13328 — Agent crashes on read_many_files tool not found
- Completed: Nov 18, 2025

---

## Workarounds and Tips

### MCP Server env field validation error

**Error:** `McpServerStdio.env Field required` / `Input should be a valid list`

**Solution:** The `env` field is required and must be a list, not a dict:

```python
# WRONG
entry = {
    "name": "my-server",
    "command": "python",
    "args": ["server.py"],
    "env": {"KEY": "value"}  # Dict - will fail!
}

# CORRECT
entry = {
    "name": "my-server",
    "command": "python",
    "args": ["server.py"],
    "env": [{"name": "KEY", "value": "value"}]  # List of EnvVariable
}
```

### OAuth Authentication

Run `gemini` interactively at least once to cache credentials before using ACP:

```bash
gemini  # Interactive mode, completes OAuth flow
# Credentials cached to ~/.gemini/google_accounts.json
```

### Version Requirements

- **Gemini CLI >= 0.27.0** for stable ACP
- **agent-client-protocol >= 0.6.0** for Python SDK
- **MCP SDK 1.26+** for `InitializationOptions` with `ServerCapabilities`

### Model Selection

Use `gemini-3-pro-preview` for best MCP tool support:

```bash
gemini --experimental-acp --yolo --model gemini-3-pro-preview
```

`gemini-2.5-pro` may have MCP visibility issues.
