"""Tests for the webhook HMAC signature verification helper (ADR-022 §7, G2)."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from taskforce.api.routes.workflows import (
    WorkflowDefinitionRequest,
    WorkflowStepRequest,
    _resolve_webhook_secret,
    _verify_webhook_signature,
    _workflow_from_request,
)


def _sign(body: bytes, secret: str, algo: str = "sha256") -> str:
    return hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()


def test_no_secret_means_open_webhook() -> None:
    """No secret configured → webhook is intentionally open."""
    assert _verify_webhook_signature(b"any-body", {}, {}) is True


def test_inline_secret_round_trip() -> None:
    body = b'{"event":"push"}'
    secret = "topsecret"
    digest = _sign(body, secret)
    assert _verify_webhook_signature(body, {"secret": secret}, {"X-Signature": digest}) is True


def test_secret_env_resolves_via_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_HOOK_SECRET", "from-env")
    body = b"hello"
    digest = _sign(body, "from-env")
    assert (
        _verify_webhook_signature(body, {"secret_env": "MY_HOOK_SECRET"}, {"X-Signature": digest})
        is True
    )


def test_inline_secret_takes_precedence_over_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_HOOK_SECRET", "wrong")
    secret = "right"
    body = b"hello"
    digest = _sign(body, secret)
    assert (
        _verify_webhook_signature(
            body,
            {"secret": secret, "secret_env": "MY_HOOK_SECRET"},
            {"X-Signature": digest},
        )
        is True
    )


def test_missing_signature_with_secret_configured_is_rejected() -> None:
    assert _verify_webhook_signature(b"hi", {"secret": "x"}, {}) is False


def test_wrong_signature_is_rejected() -> None:
    assert _verify_webhook_signature(b"hi", {"secret": "x"}, {"X-Signature": "deadbeef"}) is False


def test_github_style_prefixed_signature_works() -> None:
    """GitHub sends ``sha256=<hex>``; verifier must strip the prefix."""
    body = b'{"action":"opened"}'
    secret = "gh-secret"
    digest = _sign(body, secret)
    assert (
        _verify_webhook_signature(
            body,
            {
                "secret": secret,
                "signature_header": "X-Hub-Signature-256",
            },
            {"X-Hub-Signature-256": f"sha256={digest}"},
        )
        is True
    )


def test_prefix_mismatch_with_algo_is_rejected() -> None:
    body = b"x"
    secret = "s"
    digest = _sign(body, secret)  # sha256
    assert (
        _verify_webhook_signature(
            body,
            {"secret": secret},
            {"X-Signature": f"sha1={digest}"},  # claims sha1, body is sha256
        )
        is False
    )


def test_unsupported_algo_is_rejected() -> None:
    body = b"x"
    assert (
        _verify_webhook_signature(
            body,
            {"secret": "s", "signature_algo": "md5"},
            {"X-Signature": "irrelevant"},
        )
        is False
    )


def test_resolve_secret_returns_none_when_not_configured() -> None:
    assert _resolve_webhook_secret({}) is None


def test_resolve_secret_returns_none_when_env_var_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNDEFINED_HOOK_SECRET", raising=False)
    assert _resolve_webhook_secret({"secret_env": "UNDEFINED_HOOK_SECRET"}) is None


def test_workflow_definition_request_preserves_trigger_config_and_acp_peer() -> None:
    definition = _workflow_from_request(
        WorkflowDefinitionRequest(
            workflow_id="wf",
            name="Workflow",
            trigger="webhook",
            trigger_config={"path": "hooks/run"},
            steps=[
                WorkflowStepRequest(
                    step_id="remote",
                    agent="butler",
                    task="Run remote step",
                    acp_peer="peer-1",
                )
            ],
        )
    )

    assert definition.trigger_config == {"path": "hooks/run"}
    assert definition.steps[0].acp_peer == "peer-1"
