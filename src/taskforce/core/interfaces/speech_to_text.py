"""Protocol for speech-to-text transcription services.

Defines the contract for converting audio data to text. Implementations
can use any STT provider (OpenAI Whisper, Azure, local models, etc.)
while consumers depend only on this protocol.
"""

from __future__ import annotations

from typing import Protocol


class SpeechToTextProtocol(Protocol):
    """Protocol for speech-to-text transcription services."""

    async def transcribe(
        self,
        audio_data: bytes,
        *,
        file_name: str = "audio.ogg",
        language: str | None = None,
    ) -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_data: Raw audio file bytes (OGG, MP3, WAV, etc.).
            file_name: File name with extension for format hint.
            language: Optional ISO-639-1 language code hint (e.g. "de", "en").

        Returns:
            Transcribed text string.

        Raises:
            TaskforceError: If transcription fails.
        """
        ...
