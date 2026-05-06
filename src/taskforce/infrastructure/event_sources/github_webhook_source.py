"""GitHub webhook source — HMAC-verified, normalized payloads.

GitHub signs every webhook with the configured secret as
``X-Hub-Signature-256: sha256=<hex>``. This source:

1. Verifies the signature in constant time (raises ``ValueError`` on
   mismatch — the route translates that to ``HTTP 401``).
2. Reads the ``X-GitHub-Event`` header to label the event source
   (``github.pull_request``, ``github.issues``, ``github.push``...).
3. Extracts a small, stable subset of fields into the payload so rules
   can match on ``event.payload.action``, ``event.payload.title``,
   ``event.payload.repo``, ``event.payload.actor`` regardless of
   GitHub's ever-evolving full payload shape.

The full GitHub payload is preserved under ``payload["raw"]`` for
advanced rules that need it.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from taskforce.core.domain.agent_event import AgentEvent, AgentEventType
from taskforce.infrastructure.event_sources.webhook_source import WebhookEventSource

logger = structlog.get_logger(__name__)

EventCallback = Callable[[AgentEvent], Awaitable[None]]


class InvalidSignatureError(ValueError):
    """Raised when the GitHub HMAC signature does not match.

    The events route catches this and returns ``HTTP 401`` so the
    sender sees a precise error instead of a generic 500.
    """


class GitHubWebhookEventSource(WebhookEventSource):
    """Webhook source specialized for GitHub deliveries.

    Set ``require_signature=True`` (the default) for any deployment
    that exposes the events endpoint to the internet. Disabling it is
    only sensible inside a trusted network.
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
        require_signature: bool = True,
        event_callback: EventCallback | None = None,
        source_name: str = "github",
    ) -> None:
        super().__init__(event_callback=event_callback, source_name=source_name)
        self._secret = secret.encode("utf-8") if secret else None
        self._require_signature = require_signature

    async def handle_inbound(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        *,
        raw_body: bytes | None = None,
    ) -> AgentEvent:
        """Verify the HMAC signature and produce a normalized AgentEvent.

        ``raw_body`` is needed for HMAC verification because the GitHub
        signature is computed over the exact bytes that were sent — JSON
        re-serialization would change whitespace and break the digest.
        The events route therefore passes the request body through.
        """
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        if self._require_signature:
            signature = hdrs.get("x-hub-signature-256", "")
            if not self._verify_signature(signature, raw_body):
                raise InvalidSignatureError(
                    "GitHub webhook signature verification failed."
                )

        gh_event = hdrs.get("x-github-event", "unknown")
        delivery_id = hdrs.get("x-github-delivery", "")

        normalized = _normalize_payload(gh_event, payload)
        normalized.update(
            {
                "github_event": gh_event,
                "delivery_id": delivery_id,
                "raw": payload,
            }
        )

        event = AgentEvent(
            source=f"{self._source_name}.{gh_event}",
            event_type=AgentEventType.WEBHOOK_RECEIVED,
            payload=normalized,
            metadata={
                "headers": {k: v for k, v in hdrs.items() if k.startswith("x-github-")}
            },
        )
        logger.info(
            "github_webhook_source.event_received",
            github_event=gh_event,
            delivery_id=delivery_id,
            event_id=event.event_id,
        )
        if self._event_callback:
            await self._event_callback(event)
        return event

    def _verify_signature(self, signature_header: str, raw_body: bytes | None) -> bool:
        """Constant-time HMAC-SHA256 verification.

        Returns ``False`` when the secret is missing, the header is
        malformed, or the body is empty — all of which translate to a
        rejected request when ``require_signature=True``.
        """
        if not self._secret or not signature_header.startswith("sha256="):
            return False
        if raw_body is None:
            return False
        digest = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        expected = "sha256=" + digest
        return hmac.compare_digest(expected, signature_header)

    @classmethod
    def from_config(
        cls,
        config: dict[str, Any],
        *,
        event_callback: EventCallback | None = None,
    ) -> GitHubWebhookEventSource:
        """Factory used by ``EventSourceRegistry``.

        ``secret_env`` is preferred over ``secret`` so credentials stay
        out of YAML.
        """
        import os

        secret = config.get("secret")
        if not secret and config.get("secret_env"):
            secret = os.environ.get(config["secret_env"])
        return cls(
            secret=secret,
            require_signature=bool(config.get("require_signature", True)),
            event_callback=event_callback,
            source_name=config.get("source_name", "github"),
        )


def _normalize_payload(gh_event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Pull out a small, stable surface for rule matching.

    Falls back to empty strings for missing fields so rules using
    ``$contains`` or ``$eq`` never crash on KeyError.
    """
    repo = (payload.get("repository") or {}).get("full_name", "")
    sender = (payload.get("sender") or {}).get("login", "")
    action = payload.get("action", "")

    out: dict[str, Any] = {"action": action, "repo": repo, "actor": sender}

    if gh_event == "pull_request":
        pr = payload.get("pull_request") or {}
        out.update(
            {
                "title": pr.get("title", ""),
                "number": pr.get("number"),
                "url": pr.get("html_url", ""),
                "draft": pr.get("draft", False),
                "head_ref": (pr.get("head") or {}).get("ref", ""),
                "base_ref": (pr.get("base") or {}).get("ref", ""),
            }
        )
    elif gh_event == "issues":
        issue = payload.get("issue") or {}
        out.update(
            {
                "title": issue.get("title", ""),
                "number": issue.get("number"),
                "url": issue.get("html_url", ""),
                "labels": [lbl.get("name", "") for lbl in issue.get("labels", [])],
            }
        )
    elif gh_event == "push":
        out.update(
            {
                "ref": payload.get("ref", ""),
                "before": payload.get("before", ""),
                "after": payload.get("after", ""),
                "commits": len(payload.get("commits") or []),
            }
        )
    elif gh_event == "issue_comment":
        comment = payload.get("comment") or {}
        issue = payload.get("issue") or {}
        out.update(
            {
                "comment_body": comment.get("body", ""),
                "issue_number": issue.get("number"),
                "url": comment.get("html_url", ""),
            }
        )

    return out
