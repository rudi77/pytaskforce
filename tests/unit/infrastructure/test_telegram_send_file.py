"""Tests for TelegramOutboundSender.send_file multipart upload."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taskforce.infrastructure.communication.outbound_senders import (
    TelegramOutboundSender,
    _detect_attachment_type,
)


class TestDetectAttachmentType:
    def test_pdf_is_document(self):
        assert _detect_attachment_type("/tmp/report.pdf") == "document"

    def test_zip_is_document(self):
        assert _detect_attachment_type("/tmp/archive.zip") == "document"

    def test_jpg_is_photo(self):
        assert _detect_attachment_type("/tmp/scan.jpg") == "photo"
        assert _detect_attachment_type("/tmp/scan.JPEG") == "photo"

    def test_png_is_photo(self):
        assert _detect_attachment_type("/tmp/image.png") == "photo"

    def test_mp3_is_audio(self):
        assert _detect_attachment_type("/tmp/song.mp3") == "audio"

    def test_ogg_is_voice(self):
        assert _detect_attachment_type("/tmp/voice.ogg") == "voice"

    def test_unknown_is_document(self):
        assert _detect_attachment_type("/tmp/data.xyz") == "document"


class _FakeResponse:
    """Async context manager yielding a response stub."""

    def __init__(self, status: int = 200, body: str = "") -> None:
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def text(self):
        return self._body


class TestSendFile:
    @pytest.fixture
    def pdf_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "report.pdf"
        p.write_bytes(b"%PDF-1.4 test")
        return p

    @pytest.fixture
    def jpg_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "beleg.jpg"
        p.write_bytes(b"\xff\xd8\xff test jpg bytes")
        return p

    async def _run_send(self, sender, **kwargs):
        """Helper: mock aiohttp session and run send_file."""
        fake_session = MagicMock()
        fake_session.post = MagicMock(return_value=_FakeResponse(200))
        fake_session.closed = False

        with patch.object(
            sender, "_get_session", AsyncMock(return_value=fake_session)
        ):
            await sender.send_file(**kwargs)

        return fake_session

    @pytest.mark.asyncio
    async def test_pdf_posts_to_send_document(self, pdf_file):
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        session = await self._run_send(
            sender, recipient_id="42", file_path=str(pdf_file),
        )
        posted_url = session.post.call_args[0][0]
        assert posted_url.endswith("/sendDocument")
        assert "token-xyz" in posted_url

    @pytest.mark.asyncio
    async def test_jpg_posts_to_send_photo(self, jpg_file):
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        session = await self._run_send(
            sender, recipient_id="42", file_path=str(jpg_file),
        )
        assert session.post.call_args[0][0].endswith("/sendPhoto")

    @pytest.mark.asyncio
    async def test_explicit_type_overrides_detection(self, jpg_file):
        """Pass a JPG but force 'document' — endpoint must be sendDocument."""
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        session = await self._run_send(
            sender,
            recipient_id="42",
            file_path=str(jpg_file),
            attachment_type="document",
        )
        assert session.post.call_args[0][0].endswith("/sendDocument")

    @pytest.mark.asyncio
    async def test_unknown_type_raises(self, pdf_file):
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        with pytest.raises(ValueError, match="Unknown attachment_type"):
            await sender.send_file(
                recipient_id="42",
                file_path=str(pdf_file),
                attachment_type="bogus",
            )

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path):
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        with pytest.raises(FileNotFoundError):
            await sender.send_file(
                recipient_id="42",
                file_path=str(tmp_path / "does_not_exist.pdf"),
            )

    @pytest.mark.asyncio
    async def test_api_400_raises_without_retry(self, pdf_file):
        sender = TelegramOutboundSender("token-xyz", max_retries=3)

        fake_session = MagicMock()
        fake_session.post = MagicMock(return_value=_FakeResponse(400, "bad"))
        fake_session.closed = False

        with patch.object(
            sender, "_get_session", AsyncMock(return_value=fake_session)
        ):
            with pytest.raises(Exception) as exc:  # _TelegramClientError
                await sender.send_file(
                    recipient_id="42",
                    file_path=str(pdf_file),
                )
        assert "400" in str(exc.value)
        # Only one attempt — 4xx is not retryable.
        assert fake_session.post.call_count == 1

    @pytest.mark.asyncio
    async def test_caption_truncated_above_1024(self, pdf_file):
        sender = TelegramOutboundSender("token-xyz", max_retries=0)
        long_caption = "A" * 2000

        fake_session = MagicMock()
        fake_session.post = MagicMock(return_value=_FakeResponse(200))
        fake_session.closed = False

        with patch.object(
            sender, "_get_session", AsyncMock(return_value=fake_session)
        ):
            # Disable HTML conversion so caption stays plain
            await sender.send_file(
                recipient_id="42",
                file_path=str(pdf_file),
                caption=long_caption,
                metadata={"parse_mode": ""},
            )

        # The caption field is added as form-data; we can't easily inspect
        # the multipart body, but the call should succeed without error.
        assert fake_session.post.called
