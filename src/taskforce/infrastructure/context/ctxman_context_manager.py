"""CtxmanContextManager — ContextManagerProtocol adapter backed by ctxman.

Subclasses the local ``ContextManager`` to inherit message-list ownership,
snapshot building, and sub-agent bookkeeping, and replaces the budget
machinery: compression/eviction/compaction run server-side in ctxman.

Sync protocol methods (``initialize``/``restore``/``append_message``)
stage work locally; all remote I/O happens in ``prepare_for_llm()``:

1. ensure the remote session exists (lazy create with static region)
2. flush buffered messages as one batched segment append
3. render the context for the configured provider
4. rebuild the stable messages list in place from the render result,
   overlaying the locally built (dynamic) system prompt at index 0
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from typing import Any

from taskforce.core.domain.lean_agent_components.context_manager import ContextManager
from taskforce.core.interfaces.context_manager import ContextItem, ContextSnapshot
from taskforce.infrastructure.context.ctxman_client import (
    MAX_INLINE_CONTENT_BYTES,
    CtxmanBudgetExceededError,
    CtxmanClient,
    CtxmanConflictError,
    CtxmanError,
    CtxmanGoneError,
    CtxmanIncompleteUnitError,
    CtxmanPayloadTooLargeError,
    new_idempotency_key,
)
from taskforce.infrastructure.context.frame_binding import FrameBinding
from taskforce.infrastructure.context.message_segment_mapper import (
    build_static_segments,
    messages_to_segments,
)

# The dynamic system-prompt suffix (plan status, context pack, skill
# suffix) is overlaid locally and invisible to ctxman's token accounting;
# reserve headroom in the session budget to compensate.
DYNAMIC_PROMPT_HEADROOM_TOKENS = 4096


@dataclass(frozen=True)
class CtxmanConfig:
    """Parsed ``context_management.ctxman`` profile section."""

    base_url: str = "http://localhost:5291"
    provider: str = "openai"
    auth_mode: str = "none"
    api_key: str | None = None
    tenant_id: str | None = None
    agent_template_id: str | None = None
    timeout_seconds: float = 30.0
    turn_advance: bool = True
    on_unavailable: str = "degrade"
    gc_on_hard_watermark: bool = True
    frames_enabled: bool = True
    archive_on_close: bool = True

    @classmethod
    def from_dict(cls, config: dict[str, Any] | None) -> CtxmanConfig:
        config = config or {}
        frames = config.get("frames") or {}
        on_unavailable = str(config.get("on_unavailable", "degrade"))
        if on_unavailable not in ("degrade", "fail"):
            raise ValueError(
                f"context_management.ctxman.on_unavailable must be "
                f"'degrade' or 'fail', got: {on_unavailable!r}"
            )
        return cls(
            base_url=str(config.get("base_url", cls.base_url)),
            provider=str(config.get("provider", cls.provider)),
            auth_mode=str(config.get("auth_mode", cls.auth_mode)),
            api_key=os.environ.get("TASKFORCE_CTXMAN_API_KEY") or config.get("api_key"),
            tenant_id=config.get("tenant_id"),
            agent_template_id=config.get("agent_template_id"),
            timeout_seconds=float(config.get("timeout_seconds", cls.timeout_seconds)),
            turn_advance=bool(config.get("turn_advance", cls.turn_advance)),
            on_unavailable=on_unavailable,
            gc_on_hard_watermark=bool(config.get("gc_on_hard_watermark", cls.gc_on_hard_watermark)),
            frames_enabled=bool(frames.get("enabled", cls.frames_enabled)),
            archive_on_close=bool(config.get("archive_on_close", cls.archive_on_close)),
        )


class CtxmanContextManager(ContextManager):
    """ContextManagerProtocol implementation backed by the ctxman service."""

    def __init__(
        self,
        *,
        client: CtxmanClient,
        provider: str = "openai",
        on_unavailable: str = "degrade",
        turn_advance: bool = True,
        gc_on_hard_watermark: bool = True,
        agent_template_id: str | None = None,
        frame_binding: FrameBinding | None = None,
        frames_enabled: bool = True,
        archive_on_close: bool = True,
        owns_client: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._frames_enabled = frames_enabled
        self._archive_on_close = archive_on_close
        self._client = client
        self._provider = provider
        self._on_unavailable = on_unavailable
        self._turn_advance = turn_advance
        self._gc_on_hard_watermark = gc_on_hard_watermark
        self._agent_template_id = agent_template_id
        self._frame_binding = frame_binding
        self._owns_client = owns_client and frame_binding is None

        self._session_id: str | None = None
        self._context_version: int = 0
        self._static_hash: str | None = None
        self._base_system_prompt: str = ""
        self._outbox: list[dict[str, Any]] = []
        # In-flight batch kept separate from the outbox so a retry replays
        # the exact same segments under the same idempotency key.
        self._pending_batch: tuple[str, list[dict[str, Any]]] | None = None
        self._flush_seq: int = 0
        self._last_tokens_total: int | None = None
        self._last_watermark: str = "ok"
        self._sync_lock = asyncio.Lock()

        # Conversation-scoped session reuse (#457). The ctxman session id is
        # persisted in the agent's per-conversation state dict — viable because
        # the executor session_id == conversation_id since #453/#454. On a
        # follow-up turn we attach to the existing session and stage only the
        # new user turn; ctxman already holds the prior turns because every
        # turn flushes its final assistant answer on close (#463). The saved
        # flush sequence is continued so append idempotency keys don't collide
        # (ctxman dedups appends per batch key, not per segment).
        self._persist_state: dict[str, Any] | None = None
        self._mission: str = ""
        self._resuming: bool = False

    # ------------------------------------------------------------------
    # Lifecycle (sync — stage locally, defer remote I/O)
    # ------------------------------------------------------------------

    def initialize(
        self,
        mission: str,
        state: dict[str, Any],
        base_system_prompt: str,
    ) -> None:
        super().initialize(mission, state, base_system_prompt)
        self._base_system_prompt = base_system_prompt
        self._persist_state = state
        self._mission = mission
        self._reset_remote_state()
        self._stage_history()

    def restore(self, messages: list[dict[str, Any]]) -> None:
        super().restore(messages)
        self._base_system_prompt = self._last_system_prompt
        # ask_user resume mid-turn rebuilds a fresh session from the restored
        # messages — conversation-scoped reuse (#457) only applies to a new
        # turn via ``initialize``.
        self._reset_remote_state(allow_resume=False)
        self._stage_history()

    def _reset_remote_state(self, *, allow_resume: bool = True) -> None:
        # A fresh session is created lazily on the next prepare_for_llm;
        # frame-bound adapters attach to the parent's session instead.
        self._resuming = False
        saved = self._persisted_session() if allow_resume else None
        if self._frame_binding is not None:
            self._session_id = self._frame_binding.session_id
            self._flush_seq = 0
        elif saved is not None:
            # Conversation already has a ctxman session (#457): attach to it
            # and continue its flush sequence so append idempotency keys don't
            # collide with earlier turns (ctxman replays a colliding key and
            # silently drops the new payload).
            self._session_id = saved["session_id"]
            self._flush_seq = int(saved.get("flush_seq", 0))
            self._resuming = True
        else:
            self._session_id = None
            self._flush_seq = 0
        self._static_hash = None
        self._outbox.clear()
        self._pending_batch = None
        self._last_tokens_total = None
        self._last_watermark = "ok"

    def _persisted_session(self) -> dict[str, Any] | None:
        """Return the saved ctxman session record for this conversation, if any.

        Frame-bound adapters never own a persisted session (they ride the
        parent's), and a missing/empty state dict means a fresh session.
        """
        if self._frame_binding is not None or self._persist_state is None:
            return None
        record = self._persist_state.get("_ctxman_session")
        if isinstance(record, dict) and record.get("session_id"):
            return record
        return None

    def _persist_session_record(self) -> None:
        """Persist the ctxman session id + flush cursor into the conversation
        state so the next turn reuses the same session (#457)."""
        if (
            self._frame_binding is not None
            or self._persist_state is None
            or self._session_id is None
        ):
            return
        self._persist_state["_ctxman_session"] = {
            "session_id": self._session_id,
            "flush_seq": self._flush_seq,
        }

    def _discard_persisted_session(self) -> None:
        """Forget the persisted session and re-stage the full history into a
        fresh session — used when the saved session expired / was GC'd."""
        self._session_id = None
        self._flush_seq = 0
        self._resuming = False
        self._static_hash = None
        self._outbox.clear()
        self._pending_batch = None
        if self._persist_state is not None:
            self._persist_state.pop("_ctxman_session", None)
        self._stage_history()

    def _stage_history(self) -> None:
        """Queue messages for the first remote flush.

        Fresh session: stage the full non-system history (e.g. turn 1, or a
        session that expired and was re-created). Resumed session (#457): the
        prior turns already live in the ctxman session — each turn flushes its
        final assistant answer on close (#463) and intra-turn tool segments are
        flushed live — so stage only the new user turn (``mission``). Re-staging
        the full history would collide on the per-turn append idempotency key or
        duplicate, because ctxman dedups appends per batch key, not per segment.
        """
        if self._resuming:
            if self._mission:
                self._outbox.append({"role": "user", "content": self._mission})
            return
        self._outbox.extend(m for m in self._messages if m.get("role") != "system")

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def append_message(self, message: dict[str, Any]) -> None:
        super().append_message(message)
        self._outbox.append(message)

    # ------------------------------------------------------------------
    # Budget management — server-side in ctxman
    # ------------------------------------------------------------------

    async def compress(self) -> None:
        self._logger.debug("ctxman_compress_noop", reason="server_side_compaction")

    def preflight_check(self) -> None:
        self._logger.debug("ctxman_preflight_noop", reason="server_side_budget")

    # ------------------------------------------------------------------
    # LLM request building — the remote sync point
    # ------------------------------------------------------------------

    async def prepare_for_llm(
        self,
        *,
        rebuild_system_prompt: bool = True,
        apply_compression: bool = True,
        mission: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        if not self._initialized:
            self._logger.warning("prepare_for_llm_called_before_initialize")
            return

        async with self._sync_lock:
            if rebuild_system_prompt and self._build_system_prompt_fn:
                full_prompt = self._build_system_prompt_fn(
                    mission=mission,
                    state=state,
                    messages=self._messages,
                )
            else:
                full_prompt = self._last_system_prompt

            try:
                await self._ensure_session()
                await self._maybe_update_static()
                await self._flush_outbox()
                result = await self._render_with_recovery()
            except CtxmanGoneError as exc:
                # The persisted session expired / was GC'd (#457 — ctxman's
                # idempotency store has 24h retention). Drop it, fall back to
                # a fresh session with the full history re-staged, and retry
                # once before degrading.
                self._logger.warning(
                    "ctxman_session_gone_recreating",
                    error=str(exc),
                    session_id=self._session_id,
                )
                self._discard_persisted_session()
                try:
                    await self._ensure_session()
                    await self._maybe_update_static()
                    await self._flush_outbox()
                    result = await self._render_with_recovery()
                except CtxmanError as retry_exc:
                    if self._on_unavailable == "fail":
                        raise
                    self._logger.warning(
                        "ctxman_degraded_to_local_context",
                        error=str(retry_exc),
                        error_type=type(retry_exc).__name__,
                        session_id=self._session_id,
                    )
                    self.set_system_prompt(full_prompt)
                    return
            except CtxmanError as exc:
                if self._on_unavailable == "fail":
                    raise
                # Degrade: the locally cached messages are a complete,
                # valid OpenAI history — continue without server-side
                # compaction this turn; staged segments retry next flush.
                self._logger.warning(
                    "ctxman_degraded_to_local_context",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    session_id=self._session_id,
                )
                self.set_system_prompt(full_prompt)
                return

            self._apply_render(result, full_prompt)
            if (
                self._gc_on_hard_watermark
                and self._last_watermark in ("hard", "emergency")
                and self._session_id
            ):
                try:
                    await self._client.gc(self._session_id, level="major")
                except CtxmanError as exc:
                    self._logger.warning("ctxman_gc_trigger_failed", error=str(exc))

        self._logger.debug(
            "context_prepared_for_llm",
            message_count=len(self._messages),
            backend="ctxman",
            tokens_total=self._last_tokens_total,
            watermark=self._last_watermark,
        )

    async def _ensure_session(self) -> None:
        if self._session_id is not None:
            return
        policy_overrides: dict[str, Any] | None = None
        max_tokens = getattr(self._token_budgeter, "max_input_tokens", None)
        if max_tokens:
            policy_overrides = {
                "budget_tokens": max(1024, int(max_tokens) - DYNAMIC_PROMPT_HEADROOM_TOKENS),
            }
        static_segments = build_static_segments(
            self._base_system_prompt,
            self._openai_tools,
        )
        self._session_id, self._context_version = await self._client.create_session(
            static_segments=static_segments,
            policy_overrides=policy_overrides,
            agent_template_id=self._agent_template_id,
            idempotency_key=new_idempotency_key(),
        )
        self._static_hash = self._hash_static()
        self._persist_session_record()
        self._logger.info(
            "ctxman_session_created",
            session_id=self._session_id,
            static_segments=len(static_segments),
        )

    def _hash_static(self) -> str:
        return hashlib.sha256(self._base_system_prompt.encode("utf-8")).hexdigest()

    async def _maybe_update_static(self) -> None:
        """Replace the static region only when the base prompt changed."""
        if self._frame_binding is not None or self._session_id is None:
            return
        current = self._hash_static()
        if current == self._static_hash:
            return
        segments = build_static_segments(
            self._base_system_prompt,
            self._openai_tools,
        )
        try:
            data = await self._client.replace_static_segments(
                self._session_id,
                segments,
                if_match=self._context_version,
                idempotency_key=new_idempotency_key(),
            )
        except CtxmanConflictError as exc:
            # Stale version — refresh and retry once with a fresh key.
            detail = await self._client.get_session(self._session_id)
            self._context_version = int(detail.get("context_version", exc.context_version or 0))
            data = await self._client.replace_static_segments(
                self._session_id,
                segments,
                if_match=self._context_version,
                idempotency_key=new_idempotency_key(),
            )
        self._context_version = int(data.get("context_version", self._context_version))
        self._static_hash = current
        self._logger.info("ctxman_static_region_updated", session_id=self._session_id)

    async def _flush_outbox(self) -> None:
        """Flush staged messages as one batched, idempotent segment append."""
        assert self._session_id is not None
        # Retry a previously failed batch first — same key, same payload,
        # so a server-side replay is byte-identical and safe.
        if self._pending_batch is None and self._outbox:
            segments = messages_to_segments(self._outbox)
            self._outbox.clear()
            if segments:
                key = f"{self._session_id}:{self._flush_seq}"
                self._pending_batch = (key, segments)
        if self._pending_batch is None:
            return

        key, segments = self._pending_batch
        segments = await self._externalize_oversized(segments)
        try:
            _, self._context_version = await self._client.append_segments(
                self._session_id,
                segments,
                idempotency_key=key,
            )
        except CtxmanIncompleteUnitError as exc:
            # Close open units with synthetic results and retry once with a
            # fresh key (payload changed).
            for open_id in exc.open_tool_call_ids:
                segments.append(
                    {
                        "kind": "tool_result",
                        "role": "tool",
                        "tool_call_id": open_id,
                        "content": "[tool call cancelled]",
                    }
                )
            key = f"{self._session_id}:{self._flush_seq}:repair"
            self._pending_batch = (key, segments)
            _, self._context_version = await self._client.append_segments(
                self._session_id,
                segments,
                idempotency_key=key,
            )
        self._pending_batch = None
        self._flush_seq += 1
        self._persist_session_record()

    async def _externalize_oversized(
        self,
        segments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Upload >1MB segment contents as blobs, keep a short inline summary."""
        result: list[dict[str, Any]] = []
        for segment in segments:
            content = segment.get("content") or ""
            encoded = content.encode("utf-8") if isinstance(content, str) else b""
            if len(encoded) <= MAX_INLINE_CONTENT_BYTES:
                result.append(segment)
                continue
            try:
                assert self._session_id is not None
                blob_ref = await self._client.upload_blob(self._session_id, encoded)
                result.append(
                    {
                        **segment,
                        "blob_ref": blob_ref,
                        "content": content[:2000] + "\n[content externalized to blob]",
                    }
                )
            except (CtxmanPayloadTooLargeError, CtxmanError) as exc:
                self._logger.warning("ctxman_blob_upload_failed", error=str(exc))
                result.append(
                    {
                        **segment,
                        "content": content[: MAX_INLINE_CONTENT_BYTES // 2] + "\n...[truncated]",
                    }
                )
        return result

    async def _render_with_recovery(self) -> Any:
        assert self._session_id is not None
        scope = "frame" if self._frame_binding is not None else "path"
        try:
            return await self._client.render(
                self._session_id,
                provider=self._provider,
                scope=scope,
                turn_advance=self._turn_advance,
                idempotency_key=new_idempotency_key(),
            )
        except CtxmanBudgetExceededError:
            # Emergency eviction was insufficient — trigger a major GC and
            # retry once.
            await self._client.gc(self._session_id, level="major")
            await asyncio.sleep(0.3)
            return await self._client.render(
                self._session_id,
                provider=self._provider,
                scope=scope,
                turn_advance=self._turn_advance,
                idempotency_key=new_idempotency_key(),
            )

    def _apply_render(self, result: Any, full_prompt: str) -> None:
        """Rebuild the stable messages list in place from the render result."""
        self._messages.clear()
        self._messages.append({"role": "system", "content": full_prompt})
        self._messages.extend(result.messages)
        self._last_system_prompt = full_prompt
        self._context_version = result.context_version
        self._last_tokens_total = result.tokens_total
        self._last_watermark = result.watermark_state

    # ------------------------------------------------------------------
    # Page faults (expand_context_ref)
    # ------------------------------------------------------------------

    async def expand_ref(self, segment_id: str) -> dict[str, Any]:
        """Resolve an externalized segment for the expand_context_ref tool."""
        if self._session_id is None:
            return {
                "success": False,
                "error": "No active ctxman session; nothing to expand.",
            }
        try:
            data = await self._client.get_ref(self._session_id, segment_id)
            return {"success": True, "content": data.get("content", "")}
        except CtxmanGoneError as exc:
            summary = exc.summary or "Content no longer available."
            content = f"[evicted — summary] {summary}"
            if exc.origin:
                content += f"\n(origin: {exc.origin} — refetch from source if needed)"
            return {"success": True, "content": content, "evicted": True}
        except CtxmanError as exc:
            return {"success": False, "error": f"expand_context_ref failed: {exc}"}

    # ------------------------------------------------------------------
    # Frames (sub-agent lifecycle)
    # ------------------------------------------------------------------

    @property
    def frames_supported(self) -> bool:
        """Whether this adapter can host sub-agent frames."""
        return self._frames_enabled and self._frame_binding is None

    async def push_frame(self, label: str) -> FrameBinding | None:
        """Open a sub-agent frame on this session; returns the binding.

        Flushes the outbox first so the parent's pending tool_call lands
        in the root frame, not inside the new child frame. Returns None
        (degrade) when ctxman is unavailable and on_unavailable=degrade.
        """
        async with self._sync_lock:
            try:
                await self._ensure_session()
                await self._flush_outbox()
                assert self._session_id is not None
                frame_id = await self._client.push_frame(
                    self._session_id,
                    label,
                    idempotency_key=new_idempotency_key(),
                )
            except CtxmanError as exc:
                if self._on_unavailable == "fail":
                    raise
                self._logger.warning("ctxman_push_frame_degraded", error=str(exc))
                return None
        self._logger.debug("ctxman_frame_pushed", label=label, frame_id=frame_id)
        return FrameBinding(
            client=self._client,
            session_id=self._session_id,
            frame_id=frame_id,
        )

    async def pop_frame(self, binding: FrameBinding, return_content: str) -> None:
        """Close a sub-agent frame (promotion + eviction server-side)."""
        try:
            await self._client.pop_frame(
                binding.session_id,
                binding.frame_id,
                return_content=return_content,
                idempotency_key=new_idempotency_key(),
            )
        except CtxmanError as exc:
            if self._on_unavailable == "fail":
                raise
            self._logger.warning(
                "ctxman_pop_frame_degraded",
                frame_id=binding.frame_id,
                error=str(exc),
            )
            return
        self._logger.debug("ctxman_frame_popped", frame_id=binding.frame_id)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(
        self,
        *,
        include_content: bool = False,
        skill_manager: Any | None = None,
        memory_context: str | None = None,
    ) -> ContextSnapshot:
        base = super().snapshot(
            include_content=include_content,
            skill_manager=skill_manager,
            memory_context=memory_context,
        )
        status = (
            f"ctxman session={self._session_id or 'pending'} " f"watermark={self._last_watermark}"
        )
        if self._last_tokens_total is not None:
            status += f" server_tokens={self._last_tokens_total}"
        return replace(
            base,
            system_prompt=[
                *base.system_prompt,
                ContextItem(title=status, tokens=0),
            ],
        )

    # ------------------------------------------------------------------
    # Events (observability)
    # ------------------------------------------------------------------

    async def get_events(self, *, after_seq: int = -1) -> list[dict[str, Any]]:
        """Pull session events after the given cursor (empty if no session)."""
        if self._session_id is None:
            return []
        return await self._client.get_events(self._session_id, after_seq=after_seq)

    async def stream_events(
        self,
        *,
        after_seq: int = -1,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream session events via SSE (ends after the current snapshot)."""
        if self._session_id is None:
            return
        async for event in self._client.stream_events(
            self._session_id,
            after_seq=after_seq,
        ):
            yield event

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Archive the session (terminal promotion) and close the client.

        Frame-bound adapters share the parent's session and client and
        therefore do neither. Archiving is best-effort: a dev ctxman
        without a compaction model answers 503 promotion_failed, which
        must not break agent shutdown.
        """
        if not self._owns_client:
            return
        # Flush any pending segments — notably the final assistant answer,
        # which has no subsequent prepare_for_llm to flush it (the last LLM
        # call of a turn produces the answer and the loop ends). Without this
        # the conversation's session is missing every turn's reply (#463).
        if self._session_id is not None and (self._outbox or self._pending_batch):
            try:
                await self._flush_outbox()
            except CtxmanError as exc:
                self._logger.warning(
                    "ctxman_final_flush_failed",
                    session_id=self._session_id,
                    error=str(exc),
                )
        if self._archive_on_close and self._session_id is not None:
            try:
                await self._client.archive_session(
                    self._session_id,
                    idempotency_key=new_idempotency_key(),
                )
                self._logger.info(
                    "ctxman_session_archived",
                    session_id=self._session_id,
                )
            except CtxmanError as exc:
                self._logger.warning(
                    "ctxman_archive_failed",
                    session_id=self._session_id,
                    error=str(exc),
                )
        await self._client.aclose()


def build_ctxman_context_manager_factory(
    config: CtxmanConfig,
) -> Callable[..., CtxmanContextManager]:
    """Build the factory callable injected into ``Agent`` construction.

    The factory consults the task-local frame binding: when a parent
    agent published one (sequential sub-agent spawn), the new adapter
    shares the parent's client and session instead of creating its own.
    """
    from taskforce.infrastructure.context.frame_binding import get_frame_binding

    def factory(**kwargs: Any) -> CtxmanContextManager:
        binding = get_frame_binding()
        if binding is not None:
            return CtxmanContextManager(
                client=binding.client,
                provider=config.provider,
                on_unavailable=config.on_unavailable,
                turn_advance=config.turn_advance,
                gc_on_hard_watermark=config.gc_on_hard_watermark,
                frame_binding=binding,
                frames_enabled=config.frames_enabled,
                owns_client=False,
                **kwargs,
            )
        client = CtxmanClient(
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            auth_mode=config.auth_mode,
            api_key=config.api_key,
            tenant_id=config.tenant_id,
            logger=kwargs.get("logger"),
        )
        return CtxmanContextManager(
            client=client,
            provider=config.provider,
            on_unavailable=config.on_unavailable,
            turn_advance=config.turn_advance,
            gc_on_hard_watermark=config.gc_on_hard_watermark,
            agent_template_id=config.agent_template_id,
            frames_enabled=config.frames_enabled,
            archive_on_close=config.archive_on_close,
            **kwargs,
        )

    return factory
