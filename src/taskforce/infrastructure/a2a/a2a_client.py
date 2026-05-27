"""Outbound A2A client implementation.

Wraps ``a2a.client.Client`` so the rest of pytaskforce works with our
SDK-agnostic domain types (:class:`A2aPeer`, :class:`A2aTaskHandle`,
:class:`A2aAgentCard`). One httpx ``AsyncClient`` is pooled per peer;
agent cards are cached so we resolve them at most once per peer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from taskforce.core.domain.a2a import (
    A2aAgentCard,
    A2aArtifact,
    A2aAuthType,
    A2aPeer,
    A2aPushConfig,
    A2aSkill,
    A2aTaskHandle,
    A2aTaskState,
    A2aTransport,
)
from taskforce.infrastructure.a2a._sdk import (
    load_card_resolver,
    load_client_config,
    load_client_factory,
    load_httpx,
    load_types,
)

logger = structlog.get_logger(__name__)


class A2aClient:
    """A2A client built on ``a2a.client.Client`` with per-peer pools.

    Threadsafe enough for asyncio: an :class:`asyncio.Lock` guards the
    per-peer initialisation path so concurrent ``run_sync`` calls share
    one httpx session and one resolved card.
    """

    def __init__(
        self,
        *,
        auth_manager: Any | None = None,
        artifact_dir: str | None = None,
    ) -> None:
        self._auth_manager = auth_manager
        self._artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._httpx_pool: dict[str, Any] = {}
        self._card_pool: dict[str, A2aAgentCard] = {}
        self._raw_card_pool: dict[str, Any] = {}
        # Locks are keyed by (peer.name, loop_id) so a cached lock bound
        # to a closed loop (e.g. across test cases or successive
        # asyncio.run() calls reusing the same A2aClient) is replaced
        # rather than re-acquired and crashing with 'attached to a
        # different loop'.
        self._locks: dict[tuple[str, int], asyncio.Lock] = {}

    async def fetch_agent_card(self, peer: A2aPeer) -> A2aAgentCard:
        cached = self._card_pool.get(peer.name)
        if cached is not None:
            return cached
        await self._ensure_card(peer)
        return self._card_pool[peer.name]

    async def run_sync(
        self,
        peer: A2aPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        push: A2aPushConfig | None = None,
    ) -> A2aTaskHandle:
        events: list[Any] = []
        async for raw in self._send_message(peer, mission, session_id, metadata, push):
            events.append(raw)
        handle = _events_to_handle(peer, events, raw_history=events)
        if self._artifact_dir and handle.artifacts:
            persisted = self._persist_artifacts(handle.task_id or "unknown", events)
            if persisted:
                handle = A2aTaskHandle(
                    task_id=handle.task_id,
                    peer=handle.peer,
                    state=handle.state,
                    started_at=handle.started_at,
                    output_text=handle.output_text,
                    artifacts=persisted,
                    history=handle.history,
                    raw=handle.raw,
                )
        return handle

    async def run_stream(
        self,
        peer: A2aPeer,
        mission: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        push: A2aPushConfig | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for raw in self._send_message(peer, mission, session_id, metadata, push):
            yield _stream_event_to_dict(raw, peer)

    async def get_task(self, peer: A2aPeer, task_id: str) -> A2aTaskHandle:
        client = await self._client_for(peer)
        types = load_types()
        request = types.GetTaskRequest(id=task_id)
        task = await client.get_task(request)
        return _task_to_handle(peer, task)

    async def cancel_task(self, peer: A2aPeer, task_id: str) -> A2aTaskHandle:
        client = await self._client_for(peer)
        types = load_types()
        request = types.CancelTaskRequest(id=task_id)
        task = await client.cancel_task(request)
        return _task_to_handle(peer, task)

    async def resume_stream(
        self,
        peer: A2aPeer,
        task_id: str,
        *,
        reply: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        if reply is not None:
            async for event in self._send_message(
                peer, reply, session_id=task_id, metadata=None, push=None
            ):
                yield _stream_event_to_dict(event, peer)
            return
        client = await self._client_for(peer)
        types = load_types()
        request = types.SubscribeToTaskRequest(id=task_id)
        async for event in client.subscribe(request):
            yield _stream_event_to_dict(event, peer)

    async def close(self) -> None:
        for name, http in list(self._httpx_pool.items()):
            try:
                await http.aclose()
            except Exception:  # pragma: no cover - best-effort
                logger.debug("a2a.client.close_failed", peer=name)
        self._httpx_pool.clear()
        self._card_pool.clear()
        self._raw_card_pool.clear()
        self._locks.clear()

    async def _send_message(
        self,
        peer: A2aPeer,
        mission: str,
        session_id: str | None,
        metadata: dict[str, Any] | None,
        push: A2aPushConfig | None,
    ) -> AsyncIterator[Any]:
        client = await self._client_for(peer)
        types = load_types()
        message = types.Message(
            message_id=session_id or uuid4().hex,
            role=types.Role.ROLE_USER,
            parts=[types.Part(text=mission)],
        )
        if metadata:
            for k, v in metadata.items():
                message.metadata[k] = str(v)
        request = types.SendMessageRequest(message=message)
        if push and push.url:
            request.configuration.push_notification_config.url = push.url
            if push.token:
                request.configuration.push_notification_config.token = push.token
        async for event in client.send_message(request):
            yield event

    async def _client_for(self, peer: A2aPeer) -> Any:
        await self._ensure_card(peer)
        create_client = load_client_factory()
        client_config_cls = load_client_config()
        card = _routing_card(self._raw_card_pool[peer.name], peer.base_url)
        http = self._httpx_pool[peer.name]
        config = client_config_cls(httpx_client=http)
        return await create_client(agent=card, client_config=config)

    def _static_auth_headers(self, peer: A2aPeer) -> dict[str, str]:
        """Static headers — bearer/api_key with a literal/env-resolved token.

        OAuth2/OIDC tokens are NOT set here; they are resolved per-request
        through :class:`_DynamicBearerAuth` so an expired token does not
        get baked into the cached httpx.AsyncClient (the cache lives for
        the lifetime of the runtime, which exceeds typical OAuth TTLs).
        """
        auth = peer.auth
        headers: dict[str, str] = {}
        if auth.type == A2aAuthType.BEARER and auth.token:
            headers["Authorization"] = f"Bearer {auth.token}"
        elif auth.type == A2aAuthType.API_KEY and auth.token:
            headers[auth.api_key_header or "X-API-Key"] = auth.token
        return headers

    def _build_dynamic_auth(self, peer: A2aPeer) -> Any | None:
        """Return an httpx.Auth that re-fetches the OAuth2/OIDC token
        per request, or ``None`` when no dynamic auth is needed.
        """
        if peer.auth.type not in (A2aAuthType.OAUTH2, A2aAuthType.OIDC):
            return None
        return _DynamicBearerAuth(self, peer)

    async def _fetch_oauth_token(self, peer: A2aPeer) -> str | None:
        if self._auth_manager is None or not peer.auth.provider:
            if peer.auth.token:
                return peer.auth.token
            return None
        try:
            token_data = await self._auth_manager.get_token(peer.auth.provider)
        except Exception as exc:  # noqa: BLE001 - surfaced as warning
            logger.warning(
                "a2a.client.auth_manager_failed",
                peer=peer.name,
                provider=peer.auth.provider,
                error=str(exc),
            )
            return None
        if token_data is None:
            return None
        return getattr(token_data, "access_token", None)

    def _persist_artifacts(self, task_id: str, events: list[Any]) -> tuple[A2aArtifact, ...]:
        if self._artifact_dir is None:
            return ()
        out: list[A2aArtifact] = []
        target_dir = self._artifact_dir / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for event in events:
            if _which_oneof(event) != "artifact_update":
                continue
            artifact = event.artifact_update.artifact
            artifact_name = (
                str(getattr(artifact, "name", ""))
                or str(getattr(artifact, "artifact_id", ""))
                or "artifact"
            )
            path, size, mime_type = _write_artifact_to_disk(target_dir, artifact_name, artifact)
            out.append(
                A2aArtifact(
                    name=artifact_name,
                    mime_type=mime_type,
                    path=str(path) if path else "",
                    size=size,
                    description=str(getattr(artifact, "description", "") or ""),
                )
            )
        return tuple(out)

    def _lock_for(self, peer_name: str) -> asyncio.Lock:
        """Return a lock bound to the current running loop.

        Caching a single ``asyncio.Lock`` per peer name would crash with
        ``RuntimeError: ... attached to a different loop`` when the same
        A2aClient instance is reused across distinct event loops (tests
        running asyncio.run per case, repeated CLI invocations against
        a long-lived runtime). Keying by ``(name, loop_id)`` keeps
        single-loop usage fast and self-heals across loops.
        """
        loop = asyncio.get_running_loop()
        key = (peer_name, id(loop))
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def _ensure_card(self, peer: A2aPeer) -> None:
        lock = self._lock_for(peer.name)
        async with lock:
            if peer.name in self._card_pool:
                return
            if peer.preferred_transport != A2aTransport.JSON_RPC:
                logger.warning(
                    "a2a.client.transport_fallback",
                    peer=peer.name,
                    requested=peer.preferred_transport.value,
                    used="json_rpc",
                )
            if peer.auth.type == A2aAuthType.MTLS:
                raise NotImplementedError(
                    "mTLS authentication is declared in A2aAuthType but not "
                    "yet implemented; use bearer/oauth2 or a TLS sidecar."
                )
            if peer.auth.type in (A2aAuthType.BEARER, A2aAuthType.OAUTH2):
                if peer.base_url.startswith("http://"):
                    logger.warning(
                        "a2a.client.insecure_token",
                        peer=peer.name,
                        hint="Tokens over plain HTTP are readable on the wire; use HTTPS.",
                    )
            httpx = load_httpx()
            headers = self._static_auth_headers(peer)
            dyn_auth = self._build_dynamic_auth(peer)
            client_kwargs: dict[str, Any] = {
                "headers": headers,
                "timeout": httpx.Timeout(30.0),
            }
            if dyn_auth is not None:
                client_kwargs["auth"] = dyn_auth
            http = httpx.AsyncClient(**client_kwargs)
            resolver_cls = load_card_resolver()
            resolver_base_url, card_path = _card_resolver_target(peer)
            resolver = resolver_cls(
                httpx_client=http,
                base_url=resolver_base_url,
                agent_card_path=card_path,
            )
            try:
                raw_card = await resolver.get_agent_card()
            except Exception:
                # Don't leak the httpx client when card resolution fails.
                # The next call will rebuild with a fresh one rather than
                # overwriting a populated _httpx_pool slot.
                try:
                    await http.aclose()
                except Exception:  # pragma: no cover - best-effort
                    pass
                raise
            self._httpx_pool[peer.name] = http
            self._raw_card_pool[peer.name] = raw_card
            self._card_pool[peer.name] = _card_to_domain(raw_card, peer.base_url)


def _card_resolver_target(peer: A2aPeer) -> tuple[str, str]:
    """Return (base_url, card_path) tuple for the SDK's card resolver.

    Handles three cases:
      1. No override: card path stays at the well-known location.
      2. Override starts with '/' or is bare: relative to peer.base_url.
      3. Override is absolute and on a DIFFERENT host: switch the
         resolver's base_url to that host's origin (otherwise the SDK
         concatenates and produces a mangled URL like
         '/https://other.example/card.json').
    """
    if not peer.agent_card_url:
        return peer.base_url, "/.well-known/agent-card.json"
    rel = peer.agent_card_url
    if rel.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        parsed = urlparse(rel)
        override_origin = f"{parsed.scheme}://{parsed.netloc}"
        peer_origin = _origin_of(peer.base_url)
        if override_origin != peer_origin:
            path = parsed.path or "/.well-known/agent-card.json"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return override_origin, path
        # Same origin: strip the origin prefix.
        path = rel[len(override_origin) :] or "/.well-known/agent-card.json"
        return peer.base_url, path
    return peer.base_url, rel if rel.startswith("/") else f"/{rel}"


def _origin_of(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _routing_card(raw_card: Any, peer_base_url: str) -> Any:
    """Return a card copy whose supported_interfaces point at peer_base_url.

    The card advertised by the remote server may carry a public URL
    (the operator's ``a2a.server.public_url``) that is correct for
    public discovery but unroutable from this caller — e.g. when the
    same instance speaks to itself via 127.0.0.1, or when the public
    URL is fronted by a proxy this caller bypasses. Rewriting the URL
    here keeps the local httpx pool (configured for peer.base_url) and
    the SDK's outbound routing aligned without re-fetching the card.
    """
    if not getattr(raw_card, "supported_interfaces", None):
        return raw_card
    target = peer_base_url.rstrip("/")
    if all(
        getattr(iface, "url", "").rstrip("/") == target for iface in raw_card.supported_interfaces
    ):
        return raw_card
    routing = type(raw_card)()
    routing.CopyFrom(raw_card)
    for iface in routing.supported_interfaces:
        iface.url = target
    return routing


def _write_artifact_to_disk(
    target_dir: Path, name: str, artifact: Any
) -> tuple[Path | None, int, str]:
    """Persist artifact parts to disk; return (path, size, mime_type)."""
    parts = list(getattr(artifact, "parts", []) or [])
    if not parts:
        return None, 0, ""
    mime_type = ""
    blobs: list[bytes] = []
    for part in parts:
        media = getattr(part, "media_type", "")
        if media and not mime_type:
            mime_type = media
        try:
            if part.HasField("text"):
                blobs.append(part.text.encode("utf-8"))
                if not mime_type:
                    mime_type = "text/plain"
                continue
        except (ValueError, AttributeError):
            pass
        try:
            if part.HasField("raw"):
                blobs.append(bytes(part.raw))
                continue
        except (ValueError, AttributeError):
            pass
        try:
            if part.HasField("data"):
                blobs.append(_proto_to_json_bytes(part.data))
                if not mime_type:
                    mime_type = "application/json"
                continue
        except (ValueError, AttributeError):
            pass
    if not blobs:
        return None, 0, mime_type
    safe_name = name.replace("/", "_") or "artifact"
    path = target_dir / safe_name
    path.write_bytes(b"".join(blobs))
    return path, path.stat().st_size, mime_type


def _proto_to_json_bytes(data_part: Any) -> bytes:
    import json

    return json.dumps(_proto_to_dict(data_part)).encode("utf-8")


def _card_to_domain(raw_card: Any, base_url: str) -> A2aAgentCard:
    skills = tuple(
        A2aSkill(
            id=str(getattr(s, "id", "")),
            name=str(getattr(s, "name", "")),
            description=str(getattr(s, "description", "")),
            tags=tuple(getattr(s, "tags", []) or ()),
            input_modes=tuple(getattr(s, "input_modes", []) or ()),
            output_modes=tuple(getattr(s, "output_modes", []) or ()),
        )
        for s in getattr(raw_card, "skills", []) or []
    )
    capabilities = _capabilities_to_dict(getattr(raw_card, "capabilities", None))
    security_schemes = _security_schemes_to_dict(getattr(raw_card, "security_schemes", None))
    return A2aAgentCard(
        name=str(getattr(raw_card, "name", "")),
        description=str(getattr(raw_card, "description", "")),
        version=str(getattr(raw_card, "version", "")),
        url=base_url,
        skills=skills,
        transports=(A2aTransport.JSON_RPC,),
        capabilities=capabilities,
        security_schemes=security_schemes,
        raw=_proto_to_dict(raw_card),
    )


def _capabilities_to_dict(caps: Any) -> dict[str, bool]:
    if caps is None:
        return {}
    out: dict[str, bool] = {}
    for f in getattr(caps, "DESCRIPTOR", None).fields if hasattr(caps, "DESCRIPTOR") else []:
        try:
            value = getattr(caps, f.name)
            if isinstance(value, bool):
                out[f.name] = value
        except Exception:  # pragma: no cover - defensive
            continue
    return out


def _security_schemes_to_dict(schemes: Any) -> dict[str, dict[str, Any]]:
    if not schemes:
        return {}
    out: dict[str, dict[str, Any]] = {}
    try:
        for name in schemes:
            out[name] = _proto_to_dict(schemes[name])
    except Exception:  # pragma: no cover - SDK shape variance
        return {}
    return out


def _proto_to_dict(obj: Any) -> dict[str, Any]:
    try:
        from google.protobuf import json_format  # type: ignore[import-not-found]

        return json_format.MessageToDict(obj, preserving_proto_field_name=True)
    except Exception:  # pragma: no cover - fallback
        return {}


def _stream_event_to_dict(event: Any, peer: A2aPeer) -> dict[str, Any]:
    kind = _which_oneof(event)
    return {
        "peer": peer.name,
        "type": kind or "unknown",
        "raw": _proto_to_dict(event),
    }


def _which_oneof(event: Any) -> str | None:
    descriptor = getattr(event, "DESCRIPTOR", None)
    if descriptor is None:
        return None
    for name in ("task", "message", "status_update", "artifact_update"):
        try:
            if event.HasField(name):
                return name
        except (ValueError, AttributeError):
            continue
    return None


def _events_to_handle(
    peer: A2aPeer,
    events: list[Any],
    *,
    raw_history: list[Any],
) -> A2aTaskHandle:
    final_task: Any | None = None
    last_status: Any | None = None
    artifacts: list[Any] = []
    output_text_parts: list[str] = []
    for event in events:
        kind = _which_oneof(event)
        if kind == "task":
            final_task = event.task
        elif kind == "status_update":
            last_status = event.status_update
            text = _extract_text_from_status(event.status_update)
            if text:
                output_text_parts.append(text)
        elif kind == "artifact_update":
            # TaskArtifactUpdateEvent wraps the actual Artifact under
            # .artifact — _artifact_to_domain reads .parts/.name/.description
            # which only exist on the inner Artifact, not the wrapper.
            artifacts.append(event.artifact_update.artifact)
        elif kind == "message":
            text = _extract_text_from_message(event.message)
            if text:
                output_text_parts.append(text)

    state: A2aTaskState
    task_id = ""
    history: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = {}
    if last_status is not None:
        state = _state_from_status(last_status)
    elif final_task is not None:
        state = _task_state_from_proto(getattr(final_task.status, "state", 0))
    else:
        state = A2aTaskState.UNKNOWN
    if final_task is not None:
        task_id = str(getattr(final_task, "id", ""))
        history = tuple(_proto_to_dict(m) for m in getattr(final_task, "history", []) or [])
        raw = _proto_to_dict(final_task)
        if not output_text_parts:
            task_text = _extract_text_from_task(final_task)
            if task_text:
                output_text_parts.append(task_text)
    if not history:
        history = tuple(_proto_to_dict(e) for e in raw_history)
    output_artifacts = tuple(_artifact_to_domain(a) for a in artifacts)
    return A2aTaskHandle(
        task_id=task_id,
        peer=peer.name,
        state=state,
        output_text="\n".join(output_text_parts),
        artifacts=output_artifacts,
        history=history,
        raw=raw,
    )


def _task_to_handle(peer: A2aPeer, task: Any) -> A2aTaskHandle:
    state_proto = getattr(task.status, "state", 0) if getattr(task, "status", None) else 0
    state = _task_state_from_proto(state_proto)
    text = _extract_text_from_task(task)
    artifacts = tuple(_artifact_to_domain(a) for a in getattr(task, "artifacts", []) or [])
    history = tuple(_proto_to_dict(m) for m in getattr(task, "history", []) or [])
    return A2aTaskHandle(
        task_id=str(getattr(task, "id", "")),
        peer=peer.name,
        state=state,
        output_text=text,
        artifacts=artifacts,
        history=history,
        raw=_proto_to_dict(task),
    )


_TASK_STATE_MAP = {
    0: A2aTaskState.UNKNOWN,
    1: A2aTaskState.SUBMITTED,
    2: A2aTaskState.WORKING,
    3: A2aTaskState.COMPLETED,
    4: A2aTaskState.FAILED,
    5: A2aTaskState.CANCELED,
    6: A2aTaskState.INPUT_REQUIRED,
    7: A2aTaskState.REJECTED,
    8: A2aTaskState.AUTH_REQUIRED,
}


def _task_state_from_proto(value: int) -> A2aTaskState:
    return _TASK_STATE_MAP.get(int(value), A2aTaskState.UNKNOWN)


def _state_from_status(event: Any) -> A2aTaskState:
    """Extract task state from a ``TaskStatusUpdateEvent``.

    The event wraps a ``TaskStatus`` under ``.status``; for raw
    ``TaskStatus`` values we fall back to ``.state`` directly.
    """
    status = getattr(event, "status", None)
    if status is not None:
        return _task_state_from_proto(int(getattr(status, "state", 0)))
    state = getattr(event, "state", None)
    if state is None:
        return A2aTaskState.UNKNOWN
    return _task_state_from_proto(int(state))


def _extract_text_from_task(task: Any) -> str:
    chunks: list[str] = []
    for msg in getattr(task, "history", []) or []:
        text = _extract_text_from_message(msg)
        if text:
            chunks.append(text)
    status = getattr(task, "status", None)
    if status is not None:
        text = _extract_text_from_status(status)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _extract_text_from_message(message: Any) -> str:
    chunks: list[str] = []
    for part in getattr(message, "parts", []) or []:
        try:
            if part.HasField("text"):
                chunks.append(part.text)
        except (ValueError, AttributeError):
            continue
    return "\n".join(chunks)


def _extract_text_from_status(event: Any) -> str:
    """Extract message text from a ``TaskStatusUpdateEvent``.

    The event's ``status.message`` carries the text parts. For raw
    ``TaskStatus`` instances the ``message`` is reachable directly.
    """
    status = getattr(event, "status", None)
    if status is not None:
        message = getattr(status, "message", None)
    else:
        message = getattr(event, "message", None)
    if message is None:
        return ""
    return _extract_text_from_message(message)


def _artifact_to_domain(artifact: Any) -> A2aArtifact:
    mime_type = ""
    for part in getattr(artifact, "parts", []) or []:
        media = getattr(part, "media_type", "")
        if media:
            mime_type = media
            break
    return A2aArtifact(
        name=str(getattr(artifact, "name", "")) or str(getattr(artifact, "artifact_id", "")),
        mime_type=mime_type,
        path="",
        size=0,
        description=str(getattr(artifact, "description", "") or ""),
    )


class _DynamicBearerAuth:
    """httpx.Auth that re-resolves a Bearer token per request.

    Implements the ``httpx.Auth`` async flow contract via duck typing —
    we don't import ``httpx.Auth`` directly to keep ``httpx`` an
    optional, lazily-imported dependency. The SDK and the card resolver
    both honour the ``auth`` parameter on ``httpx.AsyncClient`` and
    invoke ``async_auth_flow`` on each outbound request, so a token
    that expired between requests is refreshed without rebuilding the
    cached client.
    """

    requires_request_body = False
    requires_response_body = False

    def __init__(self, client: A2aClient, peer: A2aPeer) -> None:
        self._client = client
        self._peer = peer

    def auth_flow(self, request: Any) -> Any:
        # Sync flow — not used because we install on AsyncClient, but
        # required to satisfy the httpx.Auth contract on some paths.
        yield request

    async def async_auth_flow(self, request: Any) -> Any:
        token = await self._client._fetch_oauth_token(self._peer)
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        yield request
