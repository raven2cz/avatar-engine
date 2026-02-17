"""Shared ACP session management for Gemini and Codex bridges.

Both bridges use the ACP protocol for warm sessions. This mixin provides
common session operations: capability detection, load/resume cascade,
list sessions, and resume session.

The host class must provide:
    self._acp_conn          — ACP Agent connection
    self._acp_session_id    — current session ID
    self._session_capabilities — SessionCapabilitiesInfo instance
    self.session_id         — public session ID (BaseBridge)
    self.working_dir        — project working directory
    self.timeout            — request timeout in seconds
    self.resume_session_id  — session ID to resume (Optional[str])
    self.continue_last      — whether to continue most recent session (bool)
    self._set_state()       — state setter (BaseBridge)
    self.provider_name      — provider name property (BaseBridge)
"""

import asyncio
import logging

from ..types import SessionInfo

logger = logging.getLogger(__name__)


class ACPSessionMixin:
    """Shared ACP session management for Gemini and Codex bridges."""

    def _store_acp_capabilities(self, init_resp) -> None:
        """Parse InitializeResponse into SessionCapabilitiesInfo."""
        caps = getattr(init_resp, "agent_capabilities", None)
        if not caps:
            return

        self._session_capabilities.can_load = bool(
            getattr(caps, "load_session", False)
        )

        sess_caps = getattr(caps, "session_capabilities", None)
        if sess_caps:
            self._session_capabilities.can_list = (
                getattr(sess_caps, "list", None) is not None
            )

        # can_continue_last = can list + can load (pick most recent, then load it)
        self._session_capabilities.can_continue_last = (
            self._session_capabilities.can_list
            and self._session_capabilities.can_load
        )

        logger.debug(
            f"ACP session capabilities: "
            f"list={self._session_capabilities.can_list}, "
            f"load={self._session_capabilities.can_load}"
        )

    async def _create_or_resume_acp_session(self, mcp_servers_acp: list) -> None:
        """Session creation cascade: load → new.

        If resume_session_id is set and agent supports load_session, load it.
        If continue_last is set, list sessions and load the most recent.
        Otherwise, create a new session.
        """
        from .base import BridgeState

        # Resume specific session
        if self.resume_session_id and self._session_capabilities.can_load:
            try:
                await asyncio.wait_for(
                    self._acp_conn.load_session(
                        cwd=self.working_dir,
                        mcp_servers=mcp_servers_acp,
                        session_id=self.resume_session_id,
                    ),
                    timeout=self.timeout,
                )
                self._acp_session_id = self.resume_session_id
                self.session_id = self._acp_session_id
                await self._apply_session_mode()
                self._set_state(BridgeState.READY)
                logger.info(f"Loaded session: {self._acp_session_id}")
                return
            except Exception as exc:
                logger.warning(
                    f"load_session({self.resume_session_id}) failed: {exc} "
                    f"— creating new session"
                )

        # Continue most recent session
        if self.continue_last and self._session_capabilities.can_continue_last:
            try:
                list_resp = await asyncio.wait_for(
                    self._acp_conn.list_sessions(cwd=self.working_dir),
                    timeout=self.timeout,
                )
                if list_resp.sessions:
                    most_recent = list_resp.sessions[0]
                    sid = most_recent.session_id
                    await asyncio.wait_for(
                        self._acp_conn.load_session(
                            cwd=self.working_dir,
                            mcp_servers=mcp_servers_acp,
                            session_id=sid,
                        ),
                        timeout=self.timeout,
                    )
                    self._acp_session_id = sid
                    self.session_id = self._acp_session_id
                    await self._apply_session_mode()
                    self._set_state(BridgeState.READY)
                    logger.info(f"Continued most recent session: {sid}")
                    return
                else:
                    logger.info("No previous sessions found, creating new")
            except Exception as exc:
                logger.warning(
                    f"continue_last failed: {exc} — creating new session"
                )

        # Fallback: create new session
        session_resp = await asyncio.wait_for(
            self._acp_conn.new_session(
                cwd=self.working_dir,
                mcp_servers=mcp_servers_acp,
            ),
            timeout=self.timeout,
        )
        self._acp_session_id = session_resp.session_id
        self.session_id = self._acp_session_id

        # Set session mode (e.g. "ask" for permission routing)
        await self._apply_session_mode()

        self._set_state(BridgeState.READY)

    async def _apply_session_mode(self) -> None:
        """Set session mode via ACP set_session_mode if applicable.

        Called after session creation/load. The host class should set
        self._acp_session_mode to the desired mode (e.g. "ask").
        Modes "auto"/"yolo" are the default — no call needed.
        """
        mode = getattr(self, "_acp_session_mode", None)
        if not mode or mode in ("auto", "yolo"):
            return
        if not self._acp_session_id:
            return
        try:
            await asyncio.wait_for(
                self._acp_conn.set_session_mode(
                    mode_id=mode,
                    session_id=self._acp_session_id,
                ),
                timeout=self.timeout,
            )
            logger.info(f"ACP session mode set to '{mode}'")
        except Exception as exc:
            logger.warning(
                f"set_session_mode('{mode}') failed: {exc} — "
                f"permission dialog may not work"
            )

    async def list_sessions(self) -> list[SessionInfo]:
        """List sessions via ACP list_sessions (if supported)."""
        if not self._acp_conn or not self._session_capabilities.can_list:
            return []

        try:
            resp = await asyncio.wait_for(
                self._acp_conn.list_sessions(cwd=self.working_dir),
                timeout=self.timeout,
            )
            return [
                SessionInfo(
                    session_id=str(s.session_id),
                    provider=self.provider_name,
                    cwd=str(getattr(s, "cwd", "")),
                    title=getattr(s, "title", None),
                    updated_at=getattr(s, "updated_at", None),
                )
                for s in resp.sessions
            ]
        except Exception as exc:
            logger.warning(f"list_sessions failed: {exc}")
            return []

    async def resume_session(self, session_id: str) -> bool:
        """Resume a session via ACP load_session."""
        if not self._acp_conn:
            raise RuntimeError("ACP connection not active")

        if not self._session_capabilities.can_load:
            raise NotImplementedError(
                f"{self.provider_name} agent does not support session load"
            )

        mcp_servers_acp = self._build_mcp_servers_acp()
        await asyncio.wait_for(
            self._acp_conn.load_session(
                cwd=self.working_dir,
                mcp_servers=mcp_servers_acp,
                session_id=session_id,
            ),
            timeout=self.timeout,
        )
        self._acp_session_id = session_id
        self.session_id = session_id
        logger.info(f"Resumed session: {session_id}")
        return True
