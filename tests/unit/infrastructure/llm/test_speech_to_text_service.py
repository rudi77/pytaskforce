"""Unit tests for LiteLLMSpeechToTextService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from taskforce.core.domain.errors import TaskforceError
from taskforce.infrastructure.llm.speech_to_text_service import (
    LiteLLMSpeechToTextService,
    _NamedBytesIO,
)


@pytest.fixture
def stt_service() -> LiteLLMSpeechToTextService:
    return LiteLLMSpeechToTextService(model="whisper-1")


class TestNamedBytesIO:
    def test_has_name_attribute(self) -> None:
        buf = _NamedBytesIO(b"hello", name="test.ogg")
        assert buf.name == "test.ogg"
        assert buf.read() == b"hello"


class TestLiteLLMSpeechToTextService:
    @pytest.mark.asyncio
    async def test_transcribe_success(self, stt_service: LiteLLMSpeechToTextService) -> None:
        mock_response = AsyncMock()
        mock_response.text = "Hallo, wie geht es dir?"

        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.return_value = mock_response

            result = await stt_service.transcribe(b"fake-audio-data", file_name="voice.ogg")

        assert result == "Hallo, wie geht es dir?"
        mock_transcription.assert_awaited_once()

        call_kwargs = mock_transcription.call_args.kwargs
        assert call_kwargs["model"] == "whisper-1"
        assert hasattr(call_kwargs["file"], "name")
        assert call_kwargs["file"].name == "voice.ogg"

    @pytest.mark.asyncio
    async def test_transcribe_with_language(self) -> None:
        service = LiteLLMSpeechToTextService(model="whisper-1", language="de")
        mock_response = AsyncMock()
        mock_response.text = "Guten Tag"

        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.return_value = mock_response

            result = await service.transcribe(b"audio", file_name="msg.ogg")

        assert result == "Guten Tag"
        assert mock_transcription.call_args.kwargs["language"] == "de"

    @pytest.mark.asyncio
    async def test_transcribe_language_override(self) -> None:
        service = LiteLLMSpeechToTextService(model="whisper-1", language="de")
        mock_response = AsyncMock()
        mock_response.text = "Hello"

        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.return_value = mock_response

            result = await service.transcribe(b"audio", language="en")

        assert result == "Hello"
        assert mock_transcription.call_args.kwargs["language"] == "en"

    @pytest.mark.asyncio
    async def test_transcribe_failure_raises_taskforce_error(
        self, stt_service: LiteLLMSpeechToTextService
    ) -> None:
        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.side_effect = RuntimeError("API error")

            with pytest.raises(TaskforceError, match="Speech-to-text transcription failed"):
                await stt_service.transcribe(b"audio")

    @pytest.mark.asyncio
    async def test_transcribe_empty_response(self, stt_service: LiteLLMSpeechToTextService) -> None:
        mock_response = AsyncMock()
        mock_response.text = ""

        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.return_value = mock_response

            result = await stt_service.transcribe(b"audio")

        assert result == ""

    @pytest.mark.asyncio
    async def test_custom_model(self) -> None:
        service = LiteLLMSpeechToTextService(model="azure/whisper-deployment")
        mock_response = AsyncMock()
        mock_response.text = "test"

        with patch("litellm.atranscription", new_callable=AsyncMock) as mock_transcription:
            mock_transcription.return_value = mock_response

            await service.transcribe(b"audio")

        assert mock_transcription.call_args.kwargs["model"] == "azure/whisper-deployment"
