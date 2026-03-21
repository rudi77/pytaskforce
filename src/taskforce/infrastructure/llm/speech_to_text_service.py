"""Speech-to-text service using LiteLLM (OpenAI Whisper API).

Provides an implementation of ``SpeechToTextProtocol`` that delegates to
``litellm.atranscription()`` for async audio transcription.  The default
model is ``whisper-1`` but can be overridden to use Azure deployments or
other providers supported by LiteLLM.
"""

from __future__ import annotations

import io
import time
from typing import Any

import structlog

from taskforce.core.domain.errors import TaskforceError

logger = structlog.get_logger(__name__)


class _NamedBytesIO(io.BytesIO):
    """BytesIO wrapper that carries a ``name`` attribute.

    LiteLLM / OpenAI SDK expect the file object to have a ``.name``
    so they can infer the audio format from the extension.
    """

    def __init__(self, data: bytes, name: str) -> None:
        super().__init__(data)
        self.name = name


class LiteLLMSpeechToTextService:
    """Speech-to-text transcription via LiteLLM.

    Uses ``litellm.atranscription()`` which wraps the OpenAI Whisper API
    (and compatible providers like Azure OpenAI).

    Args:
        model: Whisper model identifier (default ``"whisper-1"``).
            For Azure use ``"azure/<deployment-name>"``.
        language: Default ISO-639-1 language hint (e.g. ``"de"``).
            Can be overridden per call.
        extra_kwargs: Additional keyword arguments forwarded to
            ``litellm.atranscription()``.
    """

    def __init__(
        self,
        model: str = "whisper-1",
        language: str | None = None,
        **extra_kwargs: Any,
    ) -> None:
        self._model = model
        self._default_language = language
        self._extra_kwargs = extra_kwargs

    async def transcribe(
        self,
        audio_data: bytes,
        *,
        file_name: str = "audio.ogg",
        language: str | None = None,
    ) -> str:
        """Transcribe audio bytes to text via LiteLLM.

        Args:
            audio_data: Raw audio file bytes.
            file_name: File name with extension for format detection.
            language: Optional language hint (overrides constructor default).

        Returns:
            Transcribed text string.

        Raises:
            TaskforceError: If transcription fails.
        """
        import litellm

        file_obj = _NamedBytesIO(audio_data, name=file_name)
        lang = language or self._default_language

        kwargs: dict[str, Any] = {
            "model": self._model,
            "file": file_obj,
            **self._extra_kwargs,
        }
        if lang:
            kwargs["language"] = lang

        start = time.monotonic()
        try:
            response = await litellm.atranscription(**kwargs)
        except Exception as exc:
            logger.error(
                "speech_to_text.transcription_failed",
                model=self._model,
                file_name=file_name,
                error=str(exc),
            )
            raise TaskforceError(f"Speech-to-text transcription failed: {exc}") from exc

        elapsed = time.monotonic() - start
        text = getattr(response, "text", "") or ""

        logger.info(
            "speech_to_text.transcription_complete",
            model=self._model,
            file_name=file_name,
            language=lang,
            duration_s=round(elapsed, 2),
            text_length=len(text),
        )

        return text
