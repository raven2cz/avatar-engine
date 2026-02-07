# CLI Display Rewrite — Gemini CLI Style

> Created: 2026-02-07
> Status: Draft
> Assigned to: Codex
> Reviewer: Claude
> Branch: `cli-plan`

---

## Problem

The current CLI REPL display uses Rich `Live` for animated spinners. This fundamentally conflicts with:
1. `Prompt.ask()` input — flickering, lost characters
2. Streaming text output — overwritten responses
3. Event handlers printing during stream — thinking leaks into text

Rich `Live` is for progress bars, NOT for a REPL with interleaved input/status/streaming.

**Current state**: The REPL has been reverted to a simple non-Live baseline (direct prints only, no animations). This works correctly but has no animated spinners or real-time status updates.

---

## Solution: prompt_toolkit Based REPL

Replace Rich `Live` + `Prompt.ask` with **prompt_toolkit** — the same library IPython and many Python REPLs use. It handles input/display separation natively.

### Why prompt_toolkit
- Built for exactly this: async REPL with concurrent output
- `patch_stdout()` context manager lets background output not interfere with input
- `print_formatted_text()` for status updates that don't corrupt input line
- Used by IPython, pgcli, mycli, AWS CLI v2 — battle-tested
- Pure Python, no native deps

### Architecture

```
repl.py (REPL loop)
  - prompt_toolkit PromptSession for input
  - patch_stdout() context for safe background output
  - async streaming with clean text output

display.py (DisplayManager)
  - Remove all Live-related code (start_live, stop_live, update_live)
  - Keep ThinkingDisplay + ToolGroupDisplay as data models
  - Event handlers print via print_formatted_text() (safe with patch_stdout)
  - Three output modes:
    1. WAITING: single-line spinner (overwrite with \r)
    2. TOOL STATUS: printed lines (non-transient)
    3. TEXT STREAM: clean sequential print
```

---

## Reference: Gemini CLI Visual Patterns

Study `/home/box/git/github/gemini-cli/packages/cli/src/ui/components/`:

**LoadingIndicator.tsx**: `{spinner} {thought.subject} (esc to cancel, {elapsed}s)`
**ToolGroupMessage.tsx**: Box with list of tools, status icons per tool
**GeminiRespondingSpinner.tsx**: Braille dot animation

Target output (what we want to achieve):

```
You: Explain this project

⠋ Analyzing code structure (3s)
  ⠋ Read: src/main.py
  ✓ Read (0.3s)
  ⠋ Grep: patterns
  ✓ Grep (0.5s)
✓ Analysis complete (4s)

Assistant:
This project is a Python library that...

You: _                          <-- clean input, no flicker
```

Key behaviors:
- Spinner animates on a single line (\r overwrite), disappears when done
- Tool status lines are permanent (not transient)
- Text stream prints sequentially after all tools/thinking finish
- Input prompt is always clean — no concurrent display corruption

---

## Current Code Analysis

### What to KEEP
- `ThinkingDisplay` class — data model for thinking state (subject, phase, elapsed time)
- `ToolGroupDisplay` class — data model for tool tracking (active/completed/failed)
- `DisplayManager` event handler registration pattern (`_on_thinking`, `_on_tool`, etc.)
- `on_response_start()` / `on_response_end()` lifecycle hooks
- `_summarize_params()` helper
- All event types from `events.py` (ThinkingEvent, ToolEvent, etc.)
- `EngineState` enum

### What to REMOVE
- `start_live()` / `stop_live()` / `update_live()` — Rich Live is the root cause
- `Rich Live` import and usage
- `Rich Prompt.ask()` from repl.py — replace with prompt_toolkit `PromptSession`
- `_update_display_loop()` background task in repl.py
- Any `refresh_per_second` or `auto_refresh` settings

### What to ADD
- `prompt_toolkit` dependency in pyproject.toml `[cli]` extras
- `PromptSession` for async input in repl.py
- `patch_stdout()` context for safe background output
- Spinner animation using `sys.stdout.write('\r' + frame + ' ' + text)` pattern
- Clean transition from spinner to text output (erase spinner line before first text chunk)

---

## Implementation Steps

### Step 1: Add prompt_toolkit dependency

In `pyproject.toml`, add to `[project.optional-dependencies]`:
```toml
cli = ["click>=8.0", "rich>=13.0", "prompt-toolkit>=3.0"]
```

### Step 2: Rewrite repl.py input loop

Replace `Rich Prompt.ask()` with prompt_toolkit `PromptSession`:

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

session = PromptSession()

with patch_stdout():
    while True:
        user_input = await session.prompt_async("You: ")
        # ... handle commands, send to engine
        display.on_response_start()
        async for chunk in engine.chat_stream(user_input):
            if display.is_first_text:
                display.clear_status()  # erase spinner line
                print("Assistant:")
            print(chunk, end='', flush=True)
        print()  # newline after response
        display.on_response_end()
```

### Step 3: Rewrite DisplayManager output

Remove all Rich Live code. Replace with direct stdout writes that work with `patch_stdout()`:

```python
import sys
import threading

class DisplayManager:
    def __init__(self, emitter, console=None, verbose=False):
        # ... keep existing init
        self._spinner_active = False
        self._spinner_text = ''

    def _on_thinking(self, event):
        if event.is_complete:
            self.thinking.stop()
            return
        self.thinking.start(event)
        self._update_spinner()

    def _update_spinner(self):
        """Write spinner to stdout (safe with patch_stdout)."""
        text = self.thinking.render_text()  # plain text, no Rich
        if text:
            frame = SPINNER_FRAMES[self._frame_idx % len(SPINNER_FRAMES)]
            sys.stdout.write(f'\r{frame} {text}')
            sys.stdout.flush()
            self._spinner_active = True

    def clear_status(self):
        """Erase the spinner line before text output."""
        if self._spinner_active:
            sys.stdout.write('\r' + ' ' * 80 + '\r')
            sys.stdout.flush()
            self._spinner_active = False

    def _on_tool(self, event):
        """Print tool status lines (permanent, not transient)."""
        # Clear spinner first
        self.clear_status()
        if event.status == 'started':
            print(f'  \u280b {event.tool_name}: {_summarize_params(event.parameters)}')
        elif event.status == 'completed':
            print(f'  \u2713 {event.tool_name}')
        elif event.status == 'failed':
            print(f'  \u2717 {event.tool_name}: {event.error}')
```

### Step 4: Async spinner animation

Add a background task that animates the spinner at ~8 FPS:

```python
async def _animate_spinner(display):
    try:
        while True:
            display._update_spinner()
            display._frame_idx += 1
            await asyncio.sleep(0.125)
    except asyncio.CancelledError:
        display.clear_status()
```

Start/stop this task around each response, NOT around the whole REPL loop.

### Step 5: Clean up Rich usage

- Keep Rich `Console` for formatted output (colored text, tables, panels)
- Remove `Rich Live` import and all Live-related code
- Remove `Rich Prompt` import (replaced by prompt_toolkit)
- The `console.print()` calls for non-animated output (commands like /stats, /usage) stay as-is

---

## Files to Modify

| File | Action |
|------|--------|
| `pyproject.toml` | Add `prompt-toolkit>=3.0` to `[cli]` extras |
| `avatar_engine/cli/commands/repl.py` | Replace Prompt.ask with PromptSession, add patch_stdout, restructure response loop |
| `avatar_engine/cli/display.py` | Remove Live code, add spinner/clear_status methods, keep data models |
| `tests/test_cli_repl_lifecycle.py` | Update tests for new display API (no Live), test spinner output |
| `tests/integration/test_real_repl_display.py` | Update integration tests for non-Live display lifecycle |

---

## Testing Strategy

### Unit tests (test_cli_repl_lifecycle.py)

1. **Spinner output**: DisplayManager writes spinner text to stdout on ThinkingEvent
2. **Tool status lines**: ToolEvent prints permanent status lines
3. **clear_status()**: Erases spinner line (\r + spaces)
4. **on_response_start/end**: State transitions work correctly
5. **Events in non-REPL mode**: Events print directly (no prompt_toolkit needed)
6. **Verbose mode**: Prints thinking details
7. **Error handling**: Errors print immediately
8. **Multiple turns**: State resets correctly between turns

### Integration tests (test_real_repl_display.py)

1. **Real Gemini stream**: Events fire, text chunks arrive, no display corruption
2. **Real Claude stream**: Same as above (Claude has fewer ThinkingEvents)
3. **Multiple turns**: Each turn starts/ends cleanly
4. **Full text captured**: All text chunks received (nothing lost by display)

### Manual testing

```bash
# Test with Gemini (has rich thinking/tool events)
avatar repl -p gemini

# Test with Claude (fewer events, verify fallback spinner)
avatar repl -p claude

# Verify: no flickering, clean input, animated spinners, tool status lines
```

---

## Acceptance Criteria

1. **No flickering**: Input prompt is always clean, never corrupted by status output
2. **Animated spinner**: Braille spinner animates during thinking (\r overwrite)
3. **Tool status lines**: Tools show start/complete with icons, permanent lines
4. **Clean text streaming**: Response text prints sequentially after spinner clears
5. **Multiple turns**: Each turn starts fresh, no state leakage
6. **All providers work**: Gemini, Claude, Codex all display correctly
7. **All existing tests pass**: `python -m pytest tests/ -x -q` — zero failures
8. **New tests cover display**: Unit + integration tests for new display behavior
9. **No Rich Live**: Zero references to `Rich Live` in repl.py or display.py event handlers
10. **prompt_toolkit input**: `PromptSession.prompt_async()` replaces `Prompt.ask()`

---

## Dependencies

```
prompt-toolkit >= 3.0  (add to pyproject.toml [cli] extras)
```

prompt_toolkit is already a transitive dependency of IPython (which is in dev deps), but it must be explicitly listed for CLI users.

---

## Notes for Codex

- The baseline code (after revert) has NO animations — just direct prints. This is correct and fully functional.
- Your job is to ADD animations on top of the working baseline, NOT fix broken animations.
- Keep the existing command handling (/exit, /clear, /stats, etc.) — don't touch it.
- The event system (EventEmitter, ThinkingEvent, ToolEvent, etc.) is correct — don't modify `events.py`.
- Run `python -m pytest tests/ -x -q` after every change to ensure nothing breaks.
- Study Gemini CLI's visual patterns in `/home/box/git/github/gemini-cli/` for inspiration.
- Study Codex CLI's patterns in `/home/box/git/github/codex/codex-cli/` for comparison.
