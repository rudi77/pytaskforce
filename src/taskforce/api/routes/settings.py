"""Settings API routes — UI-managed runtime configuration.

Each "section" is an opaque JSON document. The framework defines a
catalogue of well-known section names in
:mod:`taskforce.core.domain.settings`; arbitrary names are accepted so
plugins can store their own config without core-side schema changes.

Schema validation per section happens in the consumers that read the
section (LLM provider builder, gateway registry, etc.) — keeping this
route schema-agnostic lets us roll out new sections without touching
the framework.

All endpoints require the ``system:config`` permission.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from taskforce.api.dependencies import (
    get_settings_store,
    request_has_permission,
    request_user_id,
    require_permission,
)
from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.settings_hydrator import (
    hydrate_channels_env,
    hydrate_llm_providers_env,
)
from taskforce.core.domain.settings import (
    CHANNELS,
    KNOWN_SECTIONS,
    LLM_PROVIDERS,
    BotConfig,
    BotOwnerKind,
    bots_to_section,
    parse_channels_section,
)

router = APIRouter()


def _rehydrate_for_section(section: str, store) -> None:
    """Apply side-effects after a settings section is written.

    The hydrator is fast and idempotent, so we just re-run the relevant
    portion. Channels also need lazy gateway/factory caches cleared so
    the next request rebuilds the gateway with the new credentials.
    """
    if section == LLM_PROVIDERS:
        hydrate_llm_providers_env(store)
    elif section == CHANNELS:
        hydrate_channels_env(store)
        # Drop the gateway / executor caches so the next request rebuilds
        # them with the new env-vars in scope. Lazy imports keep this
        # import-time cheap and avoid a circular dependency.
        from taskforce.api.dependencies import get_gateway, get_gateway_components

        get_gateway_components.cache_clear()
        get_gateway.cache_clear()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SettingsSectionResponse(BaseModel):
    """Representation of a single settings section."""

    name: str = Field(description="Section name (see core.domain.settings constants).")
    data: dict[str, Any] = Field(default_factory=dict, description="Section payload.")
    is_known: bool = Field(
        description=(
            "True when the section is one of the framework's catalogued sections. "
            "False indicates a plugin- or operator-defined section."
        )
    )


class SettingsListResponse(BaseModel):
    """List of section names currently present in the store."""

    sections: list[str]
    known_sections: list[str] = Field(
        description="Catalogue of well-known section names recognised by the framework."
    )


class SettingsSectionUpdate(BaseModel):
    """Request body for updating a section."""

    data: dict[str, Any] = Field(
        description="New payload. Replaces the existing section content entirely."
    )


class ConnectionTestResult(BaseModel):
    """Result of a connection-test probe."""

    ok: bool = Field(description="True when the probe completed successfully.")
    detail: str = Field(default="", description="Human-readable status message.")


class ChannelTestRequest(BaseModel):
    """Request body for sending a channel test message."""

    recipient: str = Field(
        description=(
            "Channel-specific recipient identifier (e.g. Telegram chat_id)."
        ),
    )
    message: str = Field(
        default="Taskforce test message — channel is wired up.",
        description="Message body to send.",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/settings",
    response_model=SettingsListResponse,
    summary="List settings sections",
    description=(
        "Return the section names currently stored, plus the catalogue of "
        "well-known sections the framework recognises. Sensitive section "
        "payloads are not returned by this endpoint — clients fetch them "
        "individually via `GET /settings/{section}` so the caller's "
        "permission can be enforced per request."
    ),
)
def list_settings(
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> SettingsListResponse:
    return SettingsListResponse(
        sections=store.list_sections(),
        known_sections=sorted(KNOWN_SECTIONS),
    )


@router.get(
    "/settings/{section}",
    response_model=SettingsSectionResponse,
    summary="Read a settings section",
    description=(
        "Return the JSON payload of `section`. Returns 404 if the section "
        "has never been written. The payload is returned as-is — secret "
        "fields are not redacted by the framework, so consumers that need "
        "to render them in a UI must mask them client-side."
    ),
)
def get_settings_section(
    section: str,
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> SettingsSectionResponse:
    data = store.get(section)
    if data is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="settings_section_not_found",
            message=f"Settings section '{section}' does not exist.",
        )
    return SettingsSectionResponse(
        name=section,
        data=data,
        is_known=section in KNOWN_SECTIONS,
    )


@router.put(
    "/settings/{section}",
    response_model=SettingsSectionResponse,
    summary="Replace a settings section",
    description=(
        "Replace `section`'s payload with the supplied `data` body. "
        "Existing keys not present in the new payload are removed."
    ),
)
def put_settings_section(
    section: str,
    body: SettingsSectionUpdate,
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> SettingsSectionResponse:
    store.put(section, body.data)
    _rehydrate_for_section(section, store)
    # Reflect the just-written value back so the client gets a fresh
    # snapshot without a second round-trip.
    return SettingsSectionResponse(
        name=section,
        data=store.get(section) or {},
        is_known=section in KNOWN_SECTIONS,
    )


@router.delete(
    "/settings/{section}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a settings section",
    description="Remove `section` from the store. No-op if it doesn't exist.",
)
def delete_settings_section(
    section: str,
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> None:
    store.delete(section)
    _rehydrate_for_section(section, store)


# ---------------------------------------------------------------------------
# Test-connection probes
# ---------------------------------------------------------------------------


@router.post(
    "/settings/llm-providers/{provider}/test",
    response_model=ConnectionTestResult,
    summary="Test LLM provider credentials",
    description=(
        "Probe `provider` (openai, anthropic, azure, google, ollama) by issuing "
        "a minimal completion call. Returns `ok=true` on success; otherwise the "
        "provider's error string is returned in `detail`."
    ),
)
async def test_llm_provider(
    provider: str,
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> ConnectionTestResult:
    # Hydrate first so the freshly-saved key is in scope before we probe.
    hydrate_llm_providers_env(store)
    try:
        import litellm
    except ImportError:
        return ConnectionTestResult(ok=False, detail="litellm is not installed")

    probe_models = {
        "openai": "gpt-4o-mini",
        "anthropic": "anthropic/claude-haiku-4-5-20251001",
        "google": "gemini/gemini-2.5-flash",
        "azure": None,  # provider-specific deployment id; cannot guess
        "ollama": "ollama/llama3",
    }
    model = probe_models.get(provider)
    if model is None:
        return ConnectionTestResult(
            ok=False,
            detail=(
                f"No automatic probe configured for provider '{provider}'. Issue "
                "a real request via the agent runtime to verify."
            ),
        )
    try:
        await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001 — surface the raw error to the UI
        return ConnectionTestResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
    return ConnectionTestResult(ok=True, detail=f"{provider}/{model} responded")


@router.post(
    "/settings/channels/{channel}/test",
    response_model=ConnectionTestResult,
    summary="Send a test message via a configured channel",
    description=(
        "Send `message` to `recipient` on the configured outbound sender for "
        "`channel`. Useful from the UI's channel-config page to verify the bot "
        "token / app credentials are correct."
    ),
)
async def test_channel(
    channel: str,
    body: ChannelTestRequest,
    _permission: None = Depends(require_permission("tenant:manage")),
    store=Depends(get_settings_store),
) -> ConnectionTestResult:
    # Make sure the latest credentials are in env, then rebuild the gateway.
    hydrate_channels_env(store)
    from taskforce.api.dependencies import get_gateway, get_gateway_components

    get_gateway_components.cache_clear()
    get_gateway.cache_clear()

    try:
        gateway = get_gateway()
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, detail=f"Gateway unavailable: {exc}")

    components = get_gateway_components()
    sender = components.outbound_senders.get(channel)
    # Reference ``gateway`` so the cache rebuild is observable to readers; the
    # gateway itself isn't strictly needed once we have the components.
    _ = gateway
    if sender is None:
        return ConnectionTestResult(
            ok=False,
            detail=f"No outbound sender configured for channel '{channel}'.",
        )

    try:
        await sender.send(recipient_id=body.recipient, message=body.message)
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
    return ConnectionTestResult(ok=True, detail=f"Sent to {channel}:{body.recipient}")


# ---------------------------------------------------------------------------
# Channel bots — CRUD over the CHANNELS settings section's bot pool.
#
# Authorization model:
# - GET list: every authenticated caller. Tokens of bots they don't own
#   are masked unless they hold ``tenant:manage``.
# - GET one: same — must be owner, admin, or accessing a tenant-shared bot.
# - POST / PATCH / DELETE: must be the bot's owner OR hold ``tenant:manage``.
# Tenant admins ALWAYS get full access via ``tenant:manage``.
# ---------------------------------------------------------------------------


class BotConfigPayload(BaseModel):
    """Bot config as sent by the UI (and returned by the API)."""

    id: str = Field(min_length=2, max_length=64)
    channel_type: str = Field(min_length=1, max_length=32)
    bot_token: str = Field(default="")
    owner_kind: str = Field(default="tenant", description="'tenant' or 'user'")
    owner_user_id: str | None = None
    default_agent: str | None = None
    pairing_mode: str | None = Field(
        default=None,
        description=(
            "'implicit' (owner=user, no /link), 'paired' (require /link), or "
            "'anonymous' (no per-user routing). Auto-defaults from owner_kind "
            "when omitted: user→implicit, tenant→paired."
        ),
    )
    enabled: bool = True


class BotListResponse(BaseModel):
    bots: list[BotConfigPayload]


_TENANT_PERM = "tenant:manage"


def _can_manage_bot(request: Request, bot: BotConfig) -> bool:
    """Owner OR tenant admin."""
    if request_has_permission(request, _TENANT_PERM):
        return True
    if bot.owner_kind is BotOwnerKind.USER:
        return bot.owner_user_id == request_user_id(request)
    return False


def _bot_to_payload(
    bot: BotConfig, *, mask_token: bool
) -> BotConfigPayload:
    raw = bot.mask_token() if mask_token else bot.to_dict()
    return BotConfigPayload(**raw)


def _load_bots(store) -> list[BotConfig]:
    return parse_channels_section(store.get(CHANNELS))


def _save_bots(store, bots: list[BotConfig]) -> None:
    store.put(CHANNELS, bots_to_section(bots))
    _rehydrate_for_section(CHANNELS, store)


async def _reconcile_bot_pollers() -> None:
    """Trigger the BotPollerManager to diff settings → running pollers.

    Called after every bot CRUD so changes take effect without restart.
    Defensive: a missing / unavailable manager is logged but never
    surfaces an HTTP error — the settings write succeeded.
    """
    from taskforce.api.dependencies import get_bot_poller_manager

    try:
        manager = get_bot_poller_manager()
    except Exception:  # noqa: BLE001
        manager = None
    if manager is None:
        return
    try:
        await manager.reconcile()
    except Exception:  # noqa: BLE001 — manager logs internally; don't leak to client
        import structlog

        structlog.get_logger().warning("bot_poller.reconcile_failed", exc_info=True)


def _validate_payload(payload: BotConfigPayload, *, request: Request) -> BotConfig:
    """Convert a payload into a validated BotConfig.

    Enforces owner-rule consistency: a user can only create user-owned
    bots for themselves (unless they hold ``tenant:manage``). Tenant-
    owned bots require ``tenant:manage``.
    """
    raw = payload.model_dump()
    try:
        bot = BotConfig.from_dict(raw)
    except ValueError as exc:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_bot_config",
            message=str(exc),
        ) from exc

    caller_uid = request_user_id(request)
    is_admin = request_has_permission(request, _TENANT_PERM)

    if bot.owner_kind is BotOwnerKind.TENANT and not is_admin:
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="tenant_manage_required",
            message="Creating tenant-owned bots requires tenant:manage permission.",
        )
    if (
        bot.owner_kind is BotOwnerKind.USER
        and not is_admin
        and bot.owner_user_id != caller_uid
    ):
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="cross_user_bot_forbidden",
            message=(
                "Non-admins can only create user-owned bots for their own user_id."
            ),
        )
    return bot


@router.get(
    "/settings/channels/bots",
    response_model=BotListResponse,
    summary="List configured channel bots",
    description=(
        "List every bot the caller can see: their own user-owned bots plus "
        "all tenant-shared bots. Tokens of bots the caller does not own are "
        "masked unless the caller holds ``tenant:manage``."
    ),
)
def list_bots(
    request: Request,
    store=Depends(get_settings_store),
) -> BotListResponse:
    caller_uid = request_user_id(request)
    is_admin = request_has_permission(request, _TENANT_PERM)
    visible: list[BotConfigPayload] = []
    for bot in _load_bots(store):
        if bot.owner_kind is BotOwnerKind.USER and not is_admin:
            # Other users' private bots stay hidden entirely from non-admins.
            if bot.owner_user_id != caller_uid:
                continue
        mask = not is_admin and not (
            bot.owner_kind is BotOwnerKind.USER and bot.owner_user_id == caller_uid
        )
        visible.append(_bot_to_payload(bot, mask_token=mask))
    return BotListResponse(bots=visible)


@router.post(
    "/settings/channels/bots",
    response_model=BotConfigPayload,
    status_code=status.HTTP_201_CREATED,
    summary="Add a channel bot",
)
async def create_bot(
    payload: BotConfigPayload,
    request: Request,
    store=Depends(get_settings_store),
) -> BotConfigPayload:
    new_bot = _validate_payload(payload, request=request)
    bots = _load_bots(store)
    if any(b.id == new_bot.id for b in bots):
        raise _http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="bot_id_exists",
            message=f"Bot id {new_bot.id!r} already exists.",
        )
    bots.append(new_bot)
    _save_bots(store, bots)
    await _reconcile_bot_pollers()
    return _bot_to_payload(new_bot, mask_token=False)


@router.patch(
    "/settings/channels/bots/{bot_id}",
    response_model=BotConfigPayload,
    summary="Update a channel bot",
)
async def update_bot(
    bot_id: str,
    payload: BotConfigPayload,
    request: Request,
    store=Depends(get_settings_store),
) -> BotConfigPayload:
    if payload.id != bot_id:
        raise _http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="id_mismatch",
            message=f"Path id {bot_id!r} does not match payload id {payload.id!r}.",
        )
    bots = _load_bots(store)
    existing = next((b for b in bots if b.id == bot_id), None)
    if existing is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="bot_not_found",
            message=f"Bot {bot_id!r} does not exist.",
        )
    if not _can_manage_bot(request, existing):
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
            message=f"Not allowed to modify bot {bot_id!r}.",
        )
    updated = _validate_payload(payload, request=request)
    bots = [updated if b.id == bot_id else b for b in bots]
    _save_bots(store, bots)
    await _reconcile_bot_pollers()
    return _bot_to_payload(updated, mask_token=False)


@router.delete(
    "/settings/channels/bots/{bot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a channel bot",
)
async def delete_bot(
    bot_id: str,
    request: Request,
    store=Depends(get_settings_store),
) -> None:
    bots = _load_bots(store)
    existing = next((b for b in bots if b.id == bot_id), None)
    if existing is None:
        return  # idempotent
    if not _can_manage_bot(request, existing):
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
            message=f"Not allowed to delete bot {bot_id!r}.",
        )
    bots = [b for b in bots if b.id != bot_id]
    _save_bots(store, bots)
    await _reconcile_bot_pollers()


class BotPollerStatusResponse(BaseModel):
    """Which bot pollers are currently running."""

    running_bot_ids: list[str]


@router.get(
    "/settings/channels/bot-pollers",
    response_model=BotPollerStatusResponse,
    summary="List currently running bot pollers",
    description=(
        "Returns the bot ids whose Telegram polling task is currently "
        "active in the backend. Useful for the UI to render a 'running' "
        "badge after add/edit/delete operations (which trigger hot "
        "reconcile)."
    ),
)
def get_bot_poller_status() -> BotPollerStatusResponse:
    from taskforce.api.dependencies import get_bot_poller_manager

    try:
        manager = get_bot_poller_manager()
    except Exception:  # noqa: BLE001
        manager = None
    if manager is None:
        return BotPollerStatusResponse(running_bot_ids=[])
    return BotPollerStatusResponse(running_bot_ids=manager.running_bot_ids())


@router.post(
    "/settings/channels/bots/{bot_id}/test",
    response_model=ConnectionTestResult,
    summary="Send a test message via a specific bot",
    description=(
        "Send a test message via this exact bot (by id), bypassing the "
        "channel-name default lookup. Use this from the UI to verify "
        "credentials of a specific multi-bot configuration."
    ),
)
async def test_bot(
    bot_id: str,
    body: ChannelTestRequest,
    request: Request,
    store=Depends(get_settings_store),
) -> ConnectionTestResult:
    bots = _load_bots(store)
    bot = next((b for b in bots if b.id == bot_id), None)
    if bot is None:
        raise _http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="bot_not_found",
            message=f"Bot {bot_id!r} does not exist.",
        )
    if not _can_manage_bot(request, bot):
        raise _http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
            message=f"Not allowed to test bot {bot_id!r}.",
        )

    from taskforce.api.dependencies import get_gateway, get_gateway_components

    # Rebuild the gateway so the latest bot list is picked up.
    get_gateway_components.cache_clear()
    get_gateway.cache_clear()

    try:
        components = get_gateway_components()
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, detail=f"Gateway unavailable: {exc}")

    sender = components.outbound_senders_by_bot_id.get(bot_id)
    if sender is None:
        return ConnectionTestResult(
            ok=False,
            detail=(
                f"No outbound sender wired for bot {bot_id!r}. "
                "Restart the backend if you just added the bot."
            ),
        )
    try:
        await sender.send(recipient_id=body.recipient, message=body.message)
    except Exception as exc:  # noqa: BLE001
        return ConnectionTestResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
    return ConnectionTestResult(ok=True, detail=f"Sent via bot {bot_id} to {body.recipient}")
