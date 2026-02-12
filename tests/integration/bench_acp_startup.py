"""Diagnostic benchmark: measure each phase of ACP startup.

Run with: python tests/integration/bench_acp_startup.py
"""

import asyncio
import logging
import os
import shutil
import sys
import time

# Ensure project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bench")


def _ms(start: float) -> str:
    return f"{(time.monotonic() - start) * 1000:.0f}ms"


async def bench_gemini_acp():
    """Benchmark Gemini ACP startup step by step."""

    from avatar_engine.bridges.gemini import GeminiBridge, _ACP_AVAILABLE

    logger.info(f"ACP SDK available: {_ACP_AVAILABLE}")

    if not _ACP_AVAILABLE:
        logger.error("ACP SDK not installed — cannot benchmark ACP mode")
        return

    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        logger.error("gemini CLI not found in PATH")
        return

    logger.info(f"gemini binary: {gemini_bin}")

    # ── Phase 0: Check gemini version (baseline) ──
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        gemini_bin, "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    logger.info(f"Phase 0 — gemini --version: {_ms(t0)} → {stdout.decode().strip()}")

    # ── Phase 1: Spawn ACP subprocess ──
    t1 = time.monotonic()
    cmd_args = [gemini_bin, "--experimental-acp", "--yolo"]
    env = dict(os.environ)

    acp_proc = await asyncio.create_subprocess_exec(
        *cmd_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=50 * 1024 * 1024,
    )
    logger.info(f"Phase 1 — subprocess spawned: {_ms(t1)} (PID {acp_proc.pid})")

    # ── Phase 2: connect_to_agent ──
    t2 = time.monotonic()
    from acp import PROTOCOL_VERSION, connect_to_agent
    from acp.schema import ClientCapabilities, FileSystemCapability

    class MinimalClient:
        async def on_permission_request(self, req):
            return True
        async def on_session_update(self, update):
            pass

    client = MinimalClient()
    conn = connect_to_agent(client, acp_proc.stdin, acp_proc.stdout)
    logger.info(f"Phase 2 — connect_to_agent created: {_ms(t2)}")

    # ── Phase 3: initialize() ──
    t3 = time.monotonic()

    # Also read stderr in background to see what's happening
    async def read_stderr():
        while acp_proc.stderr and acp_proc.returncode is None:
            line = await acp_proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            if text:
                logger.info(f"  STDERR [{_ms(t2)}]: {text}")

    stderr_task = asyncio.create_task(read_stderr())

    try:
        init_resp = await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(
                    fs=FileSystemCapability(
                        read_text_file=True,
                        write_text_file=True,
                    ),
                    terminal=True,
                ),
            ),
            timeout=120,
        )
        logger.info(
            f"Phase 3 — initialize() done: {_ms(t3)} "
            f"(protocol v{init_resp.protocol_version})"
        )
    except asyncio.TimeoutError:
        logger.error(f"Phase 3 — initialize() TIMEOUT after {_ms(t3)}")
        acp_proc.terminate()
        return

    # ── Phase 4: new_session() ──
    t4 = time.monotonic()
    try:
        session_resp = await asyncio.wait_for(
            conn.new_session(cwd=os.getcwd(), mcp_servers=[]),
            timeout=60,
        )
        logger.info(
            f"Phase 4 — new_session() done: {_ms(t4)} "
            f"(session_id={session_resp.session_id})"
        )
    except asyncio.TimeoutError:
        logger.error(f"Phase 4 — new_session() TIMEOUT after {_ms(t4)}")
        acp_proc.terminate()
        return

    total = time.monotonic() - t1
    logger.info(f"TOTAL ACP startup: {total * 1000:.0f}ms")

    # ── Phase 5: First chat message (optional, to see warm vs cold) ──
    t5 = time.monotonic()
    try:
        from acp.schema import AgentMessageChunk
        chunks = []
        async for update in conn.run_session(
            session_id=session_resp.session_id,
            new_message="Say hi.",
        ):
            if hasattr(update, 'content'):
                chunks.append(str(update.content) if update.content else "")
        logger.info(f"Phase 5 — first chat: {_ms(t5)} ({len(chunks)} chunks)")
    except Exception as e:
        logger.info(f"Phase 5 — first chat: {_ms(t5)} (error: {e})")

    # Cleanup
    stderr_task.cancel()
    acp_proc.terminate()
    await acp_proc.wait()

    logger.info("Done.")


async def bench_gemini_oneshot():
    """Benchmark Gemini oneshot (direct CLI invocation) for comparison."""

    gemini_bin = shutil.which("gemini")
    if not gemini_bin:
        logger.error("gemini CLI not found in PATH")
        return

    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        gemini_bin, "-p", "Say hi", "--yolo",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Read stderr in real time to see what happens during startup
    async def read_oneshot_stderr():
        while proc.stderr and proc.returncode is None:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            if text:
                logger.info(f"  oneshot stderr [{_ms(t0)}]: {text}")

    stderr_task = asyncio.create_task(read_oneshot_stderr())

    stdout_data, _ = await proc.communicate()
    stderr_task.cancel()
    elapsed = time.monotonic() - t0
    output = stdout_data.decode(errors="replace").strip()[:200]
    logger.info(f"Oneshot (gemini -p 'Say hi'): {elapsed * 1000:.0f}ms → {output}")


async def bench_node_baseline():
    """Measure raw Node.js cold start for reference."""
    import shutil
    node_bin = shutil.which("node")
    if not node_bin:
        logger.warning("node not found")
        return

    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        node_bin, "-e", "console.log('ok')",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    logger.info(f"Node.js cold start (node -e 'ok'): {_ms(t0)}")

    # Also measure gemini --help (loads full gemini-cli module tree)
    gemini_bin = shutil.which("gemini")
    if gemini_bin:
        t1 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            gemini_bin, "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        logger.info(f"gemini --help (module load): {_ms(t1)}")


async def main():
    logger.info("=" * 60)
    logger.info("ACP Startup Benchmark")
    logger.info("=" * 60)

    logger.info("")
    logger.info("--- Gemini ACP (step by step, with stderr) ---")
    await bench_gemini_acp()

    logger.info("")
    logger.info("--- Gemini Oneshot (with stderr) ---")
    await bench_gemini_oneshot()


if __name__ == "__main__":
    asyncio.run(main())
