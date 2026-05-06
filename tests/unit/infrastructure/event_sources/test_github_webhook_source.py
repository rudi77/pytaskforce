"""Phase 2 — GitHubWebhookEventSource HMAC verification + payload normalization."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from taskforce.core.domain.agent_event import AgentEventType
from taskforce.infrastructure.event_sources.github_webhook_source import (
    GitHubWebhookEventSource,
    InvalidSignatureError,
)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


@pytest.mark.asyncio
async def test_invalid_signature_raises() -> None:
    source = GitHubWebhookEventSource(secret="topsecret")
    body = json.dumps({"action": "opened"}).encode("utf-8")

    with pytest.raises(InvalidSignatureError):
        await source.handle_inbound(
            payload={"action": "opened"},
            headers={"X-Hub-Signature-256": "sha256=deadbeef"},
            raw_body=body,
        )


@pytest.mark.asyncio
async def test_valid_signature_pull_request_normalizes_payload() -> None:
    secret = "topsecret"
    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Refactor cancel path",
            "html_url": "https://github.com/x/y/pull/42",
            "draft": False,
            "head": {"ref": "feature-branch"},
            "base": {"ref": "main"},
        },
        "repository": {"full_name": "x/y"},
        "sender": {"login": "alice"},
    }
    body = json.dumps(payload).encode("utf-8")
    sig = _sign(secret, body)

    source = GitHubWebhookEventSource(secret=secret)
    event = await source.handle_inbound(
        payload=payload,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "abc-123",
        },
        raw_body=body,
    )

    assert event.event_type is AgentEventType.WEBHOOK_RECEIVED
    assert event.source == "github.pull_request"
    assert event.payload["action"] == "opened"
    assert event.payload["title"] == "Refactor cancel path"
    assert event.payload["repo"] == "x/y"
    assert event.payload["actor"] == "alice"
    assert event.payload["delivery_id"] == "abc-123"
    assert event.payload["raw"]["pull_request"]["number"] == 42


@pytest.mark.asyncio
async def test_signature_disabled_allows_missing_secret() -> None:
    """Local dev/internal networks: skip verification entirely."""
    source = GitHubWebhookEventSource(secret=None, require_signature=False)
    payload = {"action": "labeled", "issue": {"number": 7, "title": "bug"}}

    event = await source.handle_inbound(
        payload=payload,
        headers={"X-GitHub-Event": "issues"},
        raw_body=json.dumps(payload).encode("utf-8"),
    )

    assert event.payload["action"] == "labeled"
    assert event.payload["title"] == "bug"


@pytest.mark.asyncio
async def test_callback_is_invoked_on_success() -> None:
    received = []

    async def cb(event):
        received.append(event)

    secret = "topsecret"
    source = GitHubWebhookEventSource(secret=secret, event_callback=cb)
    payload = {"action": "opened", "repository": {"full_name": "x/y"}}
    body = json.dumps(payload).encode("utf-8")

    await source.handle_inbound(
        payload=payload,
        headers={
            "X-Hub-Signature-256": _sign(secret, body),
            "X-GitHub-Event": "pull_request",
        },
        raw_body=body,
    )

    assert len(received) == 1
    assert received[0].payload["repo"] == "x/y"


def test_factory_reads_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_GH_SECRET", "from-env")
    source = GitHubWebhookEventSource.from_config({"secret_env": "MY_GH_SECRET"})
    assert source._secret == b"from-env"  # noqa: SLF001 — test introspection
