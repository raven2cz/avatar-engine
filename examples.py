#!/usr/bin/env python3
"""
Avatar Engine — usage examples.

Run:  python examples.py [basic|stream|events|switch|fastapi]
"""

import asyncio
import json
import sys

from avatar_engine import AvatarEngine


async def basic_chat():
    """Simple question-answer."""
    engine = AvatarEngine("config.yaml")
    await engine.start()

    resp = await engine.chat("Ahoj! Kdo jsi?")
    print(f"[{resp.duration_ms}ms] {resp.content}")
    print(f"Session: {resp.session_id}")

    # Second message — same ACP session (Claude: stream-json, Gemini: ACP)
    # No cold start, model remembers the conversation natively
    resp2 = await engine.chat("Co jsem ti právě řekl?")
    print(f"[{resp2.duration_ms}ms] {resp2.content}")

    await engine.stop()


async def streaming():
    """Real-time text streaming."""
    engine = AvatarEngine("config.yaml")
    await engine.start()

    print(">>> ", end="", flush=True)
    async for chunk in engine.chat_stream("Vyprávěj krátký příběh o robotovi"):
        print(chunk, end="", flush=True)
    print()

    await engine.stop()


async def raw_events():
    """Monitor raw JSON events from CLI."""
    engine = AvatarEngine("config.yaml")

    def on_event(ev):
        etype = ev.get("type", "?")
        if etype == "tool_use":
            print(f"  🔧 Tool: {ev.get('tool_name')} params={ev.get('parameters')}")
        elif etype == "tool_result":
            print(f"  ✅ Result: {ev.get('output', '')[:100]}")
        elif etype == "init":
            print(f"  🚀 Session: {ev.get('session_id')}")
        elif etype == "result":
            print(f"  📊 Stats: {json.dumps(ev.get('stats', {}), indent=2)[:200]}")

    engine.on_event(on_event)
    await engine.start()

    resp = await engine.chat("Kolik je 2+2?")
    print(f"\nAnswer: {resp.content}")

    await engine.stop()


async def provider_switch():
    """Switch between Gemini and Claude at runtime."""
    engine = AvatarEngine("config.yaml")

    # Start with Gemini
    await engine.start()
    print(f"Provider: {engine.current_provider}")
    resp = await engine.chat("Řekni jednou větou, kdo jsi.")
    print(f"  → {resp.content}")

    # Switch to Claude
    await engine.switch_provider("claude")
    print(f"\nProvider: {engine.current_provider}")
    resp = await engine.chat("Řekni jednou větou, kdo jsi.")
    print(f"  → {resp.content}")

    await engine.stop()


async def fastapi_example():
    """FastAPI integration sketch (run with uvicorn)."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse
    except ImportError:
        print("pip install fastapi uvicorn")
        return

    app = FastAPI(title="Avatar API")
    engine = AvatarEngine("config.yaml")

    @app.on_event("startup")
    async def startup():
        await engine.start()

    @app.on_event("shutdown")
    async def shutdown():
        await engine.stop()

    @app.post("/chat")
    async def chat(prompt: str):
        resp = await engine.chat(prompt)
        return {
            "content": resp.content,
            "session_id": resp.session_id,
            "duration_ms": resp.duration_ms,
            "tool_calls": resp.tool_calls,
        }

    @app.post("/stream")
    async def stream(prompt: str):
        async def gen():
            async for chunk in engine.chat_stream(prompt):
                yield chunk
        return StreamingResponse(gen(), media_type="text/plain")

    print("FastAPI app created. Run with:")
    print("  uvicorn examples:app --reload")
    print("\nEndpoints:")
    print("  POST /chat?prompt=Ahoj")
    print("  POST /stream?prompt=Vyprávěj")


EXAMPLES = {
    "basic": basic_chat,
    "stream": streaming,
    "events": raw_events,
    "switch": provider_switch,
    "fastapi": fastapi_example,
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "basic"
    if name not in EXAMPLES:
        print(f"Usage: python examples.py [{' | '.join(EXAMPLES)}]")
        sys.exit(1)

    print(f"=== {name} ===\n")
    asyncio.run(EXAMPLES[name]())


if __name__ == "__main__":
    main()
