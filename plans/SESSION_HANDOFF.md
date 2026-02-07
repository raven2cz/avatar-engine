# Session Handoff — GUI Readiness Implementation

**Date**: 2026-02-07
**Branch**: `cli-plan`
**Test status**: 608 passed, 0 failed
**Uncommitted changes**: 9 files, +716/-148 lines (see below)

---

## Master Plan Location

**`plans/GUI_READINESS_PLAN.md`** — 2071-line comprehensive plan (version 2.0) covering:
- 9 GAPs (gaps to close for GUI readiness)
- Reference analysis of Gemini CLI, Claude Code, Codex CLI display patterns
- CLI display layer design
- Demo GUI specification

There's also an unrelated session management plan at `~/.claude/plans/composed-twirling-flurry.md` — IGNORE IT, it's from a different task.

---

## What Has Been Implemented (Phases 1-3 + GAP-3 fix)

### Phase 1: Thread Safety — ALL 13 race conditions fixed ✅

Every RC from GAP-4 of the plan:

| RC | What | Where | Lock type |
|----|-------|-------|-----------|
| RC-1 | Sync loop creation race | `engine.py` `_get_sync_loop()` | `threading.Lock` (`_sync_loop_lock`) |
| RC-2 | EventEmitter handler mutation during emit | `events.py` `EventEmitter` | `threading.Lock` (`_lock`), snapshot-under-lock pattern |
| RC-3/4 | ACP buffer writes from callback thread | `gemini.py`, `codex.py` | `threading.Lock` (`_acp_buffer_lock`) |
| RC-5/6 | Signal handler calling asyncio.create_task | `engine.py` `_initiate_shutdown()` | Uses `loop.call_soon_threadsafe()` instead |
| RC-7 | Concurrent stdin writes | `base.py` `_send_persistent()/_stream_persistent()` | `asyncio.Lock` (`_stdin_lock`) |
| RC-8 | Stderr buffer race | `base.py` `_monitor_stderr()/get_stderr_buffer()` | `threading.Lock` (`_stderr_lock`) |
| RC-9 | History list mutation | `base.py` + `gemini.py` + `codex.py` | `threading.Lock` (`_history_lock`) |
| RC-10 | Stats dict mutation | `base.py` `_update_stats()/get_usage()/get_stats()` | `threading.Lock` (`_stats_lock`) |
| RC-11 | Health check after shutdown | Already handled by `_shutting_down` flag |
| RC-12 | RateLimiterSync race | `utils/rate_limit.py` | `threading.Lock` (`_lock`) |
| RC-13 | Engine stop_sync race | `engine.py` `stop_sync()` | Uses `_sync_loop_lock` |

### Phase 2: ThinkingEvent Extensions ✅

New types in `events.py`:
- **`ThinkingPhase` enum**: GENERAL, ANALYZING, PLANNING, CODING, REVIEWING, TOOL_PLANNING
- **`ActivityStatus` enum**: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
- **`ThinkingEvent` extended fields**: `phase`, `subject`, `is_start`, `is_complete`, `block_id`, `token_count`, `category`
- **`ActivityEvent` dataclass**: full concurrent activity tracking event

New functions in `events.py`:
- **`extract_bold_subject(text)`** — regex `**bold**` parser, returns `(subject, description)`
- **`classify_thinking(thought)`** — keyword heuristic → `ThinkingPhase` (uses stemmed keywords like `"invok"`, `"execut"`, `"analyz"`)

Engine integration in `engine.py` `_handle_raw_event()`:
- Thinking events enriched with bold parser + phase classifier
- Synthetic `ThinkingEvent` emitted for Claude on `tool_use` (Claude CLI doesn't emit thinking)
- Tool events emit both `ToolEvent` and activity tracking

### Phase 3: ActivityTracker ✅

New file **`avatar_engine/activity.py`**:
- `ActivityTracker` class — thread-safe concurrent operation tracker
- Methods: `start_activity()`, `update_activity()`, `complete_activity()`, `fail_activity()`, `cancel_activity()`, `clear()`
- Properties: `active_count`, `active_activities`, `get_activity(id)`

Engine integration:
- `self._activity_tracker = ActivityTracker(self)` in engine `__init__`
- `activity_tracker` property exposed on engine
- Tool start/complete/fail events automatically tracked in `_handle_raw_event()`

### GAP-3: Thinking Leak Fix ✅

In `base.py` `_send_oneshot()`: added `self._on_event(event)` call for each parsed JSON event, so thinking events are emitted in oneshot mode too (previously only persistent/ACP modes emitted raw events).

### Exports ✅

`__init__.py` updated to export: `ActivityTracker`, `ActivityEvent`, `ActivityStatus`, `ThinkingPhase`, `extract_bold_subject`, `classify_thinking`

### Tests ✅

New test classes in `tests/test_events.py` (273 new lines):
- `TestThinkingPhase` — enum values
- `TestExtendedThinkingEvent` — default + full field tests
- `TestExtractBoldSubject` — 7 tests (simple, at start, in middle, no bold, empty, multiple, nested)
- `TestClassifyThinking` — all 6 phases tested
- `TestActivityEvent` — defaults + full activity
- `TestActivityTracker` — 7 tests (start/complete, fail, cancel, update, concurrent, clear, get)
- `TestEventEmitterThreadSafety` — concurrent emit+add, handler registering handler during emit

Fix in `tests/test_cli.py`: added `bridge._stats_lock = threading.Lock()` to 2 tests using `MagicMock(spec=ClaudeBridge)`.

---

## What Remains To Be Done

### Phase 4 (partially done): CLI Display Layer

GAP-3 oneshot fix is done. What's LEFT from Phase 4:

**CLI display layer** — the plan describes a `DisplayManager` for the CLI (`avatar_engine/cli/display.py`) that:
- Renders ThinkingEvents as animated status lines (spinner + phase + subject)
- Renders ActivityEvents as a tree of concurrent operations
- Handles text streaming with proper line buffering
- See `GUI_READINESS_PLAN.md` sections "GAP-5: CLI Display Layer" and "Part III: CLI Display Architecture"

### Phase 5: System Prompt Composition (GAP-6)

Plan section "GAP-6: System Prompt" — structured system prompt builder that composes:
- Base persona instructions
- Domain context from config
- Tool usage guidelines
- Output format constraints
- Currently system prompt is just a flat string passed through

### Phase 6: Diagnostics (GAP-7)

Plan section "GAP-7: Diagnostics" — structured logging, metrics collection, debug mode with event replay.

### Phase 7: Demo GUI

Plan section "Part IV: Demo GUI" — simple Textual/Rich TUI that demonstrates all the event-driven features working together. This is a showcase, not production code.

---

## Files Modified (uncommitted)

```
avatar_engine/events.py           — ThinkingPhase, ActivityStatus, ActivityEvent, bold parser, classifier, thread-safe EventEmitter
avatar_engine/engine.py           — ActivityTracker integration, enriched _handle_raw_event, thread-safe sync loop, signal handler fix
avatar_engine/bridges/base.py     — All thread safety locks (stdin, stderr, history, stats), GAP-3 oneshot fix, session capabilities
avatar_engine/bridges/gemini.py   — ACP buffer lock, history lock usage
avatar_engine/bridges/codex.py    — ACP buffer lock, history lock usage
avatar_engine/utils/rate_limit.py — RateLimiterSync thread safety
avatar_engine/__init__.py         — New exports
avatar_engine/activity.py         — NEW FILE: ActivityTracker class
tests/test_events.py              — 273 lines of new tests
tests/test_cli.py                 — Mock fixes for _stats_lock
```

---

## How to Continue

1. **Read the plan**: `plans/GUI_READINESS_PLAN.md` (the master plan with all details)
2. **Commit current work first** if user asks — all 608 tests pass, this is a clean checkpoint
3. **Next task**: Phase 4 CLI display layer, then Phase 5-7
4. **Run tests**: `python -m pytest tests/ -x -q` — should show 608 passed
5. **Branch**: `cli-plan` (based off `main`)

---

## Key Architecture Notes

- **EventEmitter uses snapshot-under-lock**: `emit()` copies handler lists under lock, calls handlers WITHOUT lock. This prevents deadlock when a handler registers new handlers.
- **Signal handler safety**: `_initiate_shutdown()` uses only `loop.call_soon_threadsafe()` — the only asyncio function safe from signal handlers.
- **Stemmed keywords in classifier**: `"invok"` not `"invoke"` (because invoke→invoking drops the 'e'), same for `"execut"` and `"analyz"`.
- **ACP bridges (Gemini + Codex)** share identical buffer lock patterns but are NOT yet refactored into a mixin (that's part of the session management plan, not this plan).
- **BaseBridge** has `SessionCapabilitiesInfo` and default `list_sessions()`/`resume_session()` methods (from the session management work done in a previous commit).
