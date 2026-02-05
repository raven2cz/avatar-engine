#!/usr/bin/env python3
"""
Basic chat example — demonstrates simple synchronous and asynchronous usage.

Usage:
    python examples/basic_chat.py
    python examples/basic_chat.py --provider claude
    python examples/basic_chat.py --async
"""

import argparse
import asyncio

from avatar_engine import AvatarEngine


def sync_example(provider: str = "gemini") -> None:
    """Synchronous chat example."""
    print(f"=== Sync Example ({provider}) ===\n")

    # Create and start engine
    engine = AvatarEngine(provider=provider)
    engine.start_sync()

    try:
        # Simple chat
        response = engine.chat_sync("What is 2 + 2? Answer briefly.")
        print(f"Response: {response.content}")
        print(f"Success: {response.success}")
        print(f"Duration: {response.duration_ms}ms")

        # Follow-up (uses conversation history)
        response = engine.chat_sync("And what is that number times 10?")
        print(f"\nFollow-up: {response.content}")

    finally:
        engine.stop_sync()
        print("\n=== Session ended ===")


async def async_example(provider: str = "gemini") -> None:
    """Asynchronous chat example."""
    print(f"=== Async Example ({provider}) ===\n")

    engine = AvatarEngine(provider=provider)
    await engine.start()

    try:
        # Simple chat
        response = await engine.chat("Tell me a one-sentence fun fact.")
        print(f"Response: {response.content}")

        # Streaming response
        print("\nStreaming response:")
        async for chunk in engine.chat_stream("Count from 1 to 5, one number per line."):
            print(chunk, end="", flush=True)
        print()

    finally:
        await engine.stop()
        print("\n=== Session ended ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic Avatar Engine chat example")
    parser.add_argument(
        "--provider", "-p",
        choices=["gemini", "claude"],
        default="gemini",
        help="AI provider to use"
    )
    parser.add_argument(
        "--async", "-a",
        dest="use_async",
        action="store_true",
        help="Use async example"
    )
    args = parser.parse_args()

    if args.use_async:
        asyncio.run(async_example(args.provider))
    else:
        sync_example(args.provider)


if __name__ == "__main__":
    main()
