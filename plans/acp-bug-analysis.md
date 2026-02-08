## ACP Bug Analysis — RESOLVED

**Status:** DONE (2026-02-08)

### Original Issue

Gemini ACP `prompt()` returned "Internal error" (HTTP 500). Filed as
[gemini-cli#18423](https://github.com/google-gemini/gemini-cli/issues/18423).

### Root Causes Found

The issue had **three** contributing factors:

#### 1. Wrong SDK API — `spawn_agent_process` vs `connect_to_agent`

We used `spawn_agent_process` (deprecated context manager) instead of the
official `connect_to_agent` API. The correct pattern from the SDK example:

```python
proc = await asyncio.create_subprocess_exec(
    *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    stderr=None, cwd=cwd, env=env,
)
conn = connect_to_agent(client, proc.stdin, proc.stdout)
```

#### 2. Missing `ClientCapabilities` in `initialize()`

We called `initialize(protocol_version=1)` without `client_capabilities`.
Gemini-cli requires the client to declare what it supports (filesystem, terminal).
Correct call:

```python
await conn.initialize(
    protocol_version=PROTOCOL_VERSION,
    client_capabilities=ClientCapabilities(
        fs=FileSystemCapability(read_text_file=True, write_text_file=True),
        terminal=True,
    ),
)
```

#### 3. Wrong `request_permission` response format

Our client returned raw dicts `{"outcome": first_option}`. The SDK expects
typed Pydantic models:

```python
RequestPermissionResponse(
    outcome=AllowedOutcome(option_id=opt.option_id, outcome="selected")
)
```

#### 4. Settings overrides (secondary, now also fixed)

- `previewFeatures` was removed from gemini-cli (commit `61d92c4a2`).
  Gemini 3 is now the default. We no longer set this flag.
- `model.name` in system settings (highest priority) bypassed the built-in
  alias chain that carries `generateContentConfig` (thinkingConfig etc.).
  ACP mode no longer writes settings at all.

### Previous Analysis (Outdated)

The original analysis about `sendMessageStream` discarding `generateContentConfig`
at line 305-306 of `geminiChat.ts` was partially correct but is no longer the
primary issue. The new gemini-cli code resolves config properly via
`applyModelSelection()` in `makeApiCallAndProcessStream()`.

### Fix Applied

- `avatar_engine/bridges/gemini.py`: Rewritten ACP startup to use
  `connect_to_agent`, `ClientCapabilities`, typed `RequestPermissionResponse`
- ACP mode no longer writes `settings.json` (no `GEMINI_CLI_SYSTEM_SETTINGS_PATH`)
- Removed `previewFeatures` (gone from gemini-cli)
- ACP SDK upgraded to 0.8.0
