"""Regression tests for gateway channel registration from environment."""

from __future__ import annotations

from taskforce.infrastructure.communication.gateway_registry import build_gateway_components
from taskforce.infrastructure.communication.outbound_senders import TelegramOutboundSender


def test_telegram_token_registers_outbound_sender(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:fake-token")

    components = build_gateway_components(work_dir=str(tmp_path))

    assert isinstance(components.outbound_senders["telegram"], TelegramOutboundSender)
    assert "telegram" in components.inbound_adapters


def test_missing_telegram_token_keeps_inbound_adapter_but_no_sender(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    components = build_gateway_components(work_dir=str(tmp_path))

    assert "telegram" not in components.outbound_senders
    assert "telegram" in components.inbound_adapters
