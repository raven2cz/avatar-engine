#!/usr/bin/env python3
"""
Streaming avatar example — demonstrates real-time avatar integration.

This example shows how to:
- Stream AI responses in real-time
- Integrate with TTS (text-to-speech) systems
- Handle conversation flow
- Use MCP tools

Usage:
    python examples/streaming_avatar.py
    python examples/streaming_avatar.py --provider claude
    python examples/streaming_avatar.py --with-tts  # Simulated TTS
"""

import argparse
import asyncio
from typing import Optional

from avatar_engine import AvatarEngine
from avatar_engine.events import TextEvent, ToolEvent


class MockTTS:
    """Simulated TTS engine for demonstration."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.queue: list[str] = []

    async def speak(self, text: str) -> None:
        """Queue text for speech synthesis."""
        if not self.enabled:
            return

        self.queue.append(text)
        # In real implementation:
        # await self.synthesizer.speak(text)
        print(f"[TTS] Speaking: {text[:50]}...")

    async def flush(self) -> None:
        """Wait for all queued speech to complete."""
        if self.queue:
            print(f"[TTS] Flushed {len(self.queue)} segments")
            self.queue.clear()


class StreamingAvatar:
    """
    Streaming avatar controller.

    Manages the connection between AI engine and avatar display/TTS.
    """

    def __init__(
        self,
        provider: str = "gemini",
        tts: Optional[MockTTS] = None,
    ):
        self.engine = AvatarEngine(provider=provider)
        self.tts = tts or MockTTS()
        self._current_response = ""
        self._sentence_buffer = ""

    async def start(self) -> None:
        """Initialize avatar."""
        # Set up event handlers
        @self.engine.on(TextEvent)
        def on_text(event: TextEvent) -> None:
            self._handle_text(event.text)

        @self.engine.on(ToolEvent)
        def on_tool(event: ToolEvent) -> None:
            if event.status == "started":
                print(f"\n[Avatar is using {event.tool_name}...]")

        await self.engine.start()
        print(f"Avatar ready (provider: {self.engine.current_provider})")

    async def stop(self) -> None:
        """Shutdown avatar."""
        await self.tts.flush()
        await self.engine.stop()
        print("Avatar shutdown complete")

    def _handle_text(self, text: str) -> None:
        """Process incoming text chunk."""
        self._current_response += text
        self._sentence_buffer += text

        # Check for sentence boundaries for TTS
        if self.tts.enabled:
            while True:
                # Find sentence end
                for end in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
                    idx = self._sentence_buffer.find(end)
                    if idx != -1:
                        sentence = self._sentence_buffer[: idx + len(end)]
                        self._sentence_buffer = self._sentence_buffer[idx + len(end) :]
                        # Queue for TTS (non-blocking)
                        asyncio.create_task(self.tts.speak(sentence.strip()))
                        break
                else:
                    break

    async def chat(self, message: str) -> str:
        """
        Send message to avatar and stream response.

        Returns the complete response.
        """
        self._current_response = ""
        self._sentence_buffer = ""

        print(f"\nYou: {message}")
        print("Avatar: ", end="", flush=True)

        async for chunk in self.engine.chat_stream(message):
            print(chunk, end="", flush=True)

        print()

        # Flush any remaining text to TTS
        if self._sentence_buffer.strip():
            await self.tts.speak(self._sentence_buffer.strip())
        await self.tts.flush()

        return self._current_response

    async def interactive_session(self) -> None:
        """Run interactive conversation session."""
        print("\n=== Interactive Avatar Session ===")
        print("Type 'quit' to exit, 'clear' to reset history\n")

        while True:
            try:
                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit"):
                    break
                if user_input.lower() == "clear":
                    self.engine.clear_history()
                    print("[History cleared]")
                    continue

                await self.chat(user_input)

            except KeyboardInterrupt:
                print("\n[Interrupted]")
                break
            except EOFError:
                break


async def main() -> None:
    """Run streaming avatar demo."""
    parser = argparse.ArgumentParser(description="Streaming Avatar Example")
    parser.add_argument(
        "--provider", "-p",
        choices=["gemini", "claude", "codex"],
        default="gemini",
        help="AI provider"
    )
    parser.add_argument(
        "--with-tts",
        action="store_true",
        help="Enable simulated TTS"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run interactive session"
    )
    args = parser.parse_args()

    # Create avatar
    tts = MockTTS(enabled=args.with_tts)
    avatar = StreamingAvatar(provider=args.provider, tts=tts)

    try:
        await avatar.start()

        if args.interactive:
            await avatar.interactive_session()
        else:
            # Demo conversation
            await avatar.chat("Hello! Introduce yourself briefly.")
            await avatar.chat("What can you help me with?")

    finally:
        await avatar.stop()


if __name__ == "__main__":
    asyncio.run(main())
