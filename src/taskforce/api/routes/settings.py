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

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from taskforce.api.dependencies import get_settings_store, require_permission
from taskforce.api.errors import http_exception as _http_exception
from taskforce.application.settings_hydrator import (
    hydrate_channels_env,
    hydrate_llm_providers_env,
)
from taskforce.core.domain.settings import CHANNELS, KNOWN_SECTIONS, LLM_PROVIDERS

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
