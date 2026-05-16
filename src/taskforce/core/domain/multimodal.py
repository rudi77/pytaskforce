"""Multimodal content helpers (domain layer).

Shared utilities for turning an `attachments` list into OpenAI-compatible
multimodal content blocks. Used in both directions:

- **Inbound**: gateway translates user-uploaded images/documents into a
  user message with `image_url` blocks before the agent sees the mission.
- **Outbound**: tool-result message factory translates images returned by
  tools (e.g. `multimedia`) into a follow-up user message so vision-capable
  LLMs can actually *see* them.

Attachment shape::

    {
        "type": "image" | "document",
        "data_url": "data:image/jpeg;base64,...",   # for images
        "file_path": "/tmp/foo.jpg",                # optional, both types
        "file_name": "foo.jpg",                     # optional
        "mime_type": "image/jpeg",                  # for documents
    }
"""

from __future__ import annotations

from typing import Any


def build_multimodal_content(
    text: str,
    attachments: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    """Build OpenAI-compatible content from text and optional attachments.

    If there are no attachments, returns plain ``text``. For image
    attachments, returns a content array with text and ``image_url``
    blocks. For document attachments, appends file-path references to
    the text so the agent can use file tools.

    Args:
        text: Caption / surrounding text.
        attachments: Optional list of attachment dicts.

    Returns:
        Plain string when no images are present (so existing string-content
        code paths stay unchanged), otherwise an OpenAI vision-format
        content array.
    """
    if not attachments:
        return text

    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    doc_references: list[str] = []

    for att in attachments:
        att_type = att.get("type")
        if att_type == "image" and att.get("data_url"):
            parts.append({"type": "image_url", "image_url": {"url": att["data_url"]}})
            if att.get("file_path"):
                file_path = att["file_path"]
                file_name = att.get("file_name", "image")
                doc_references.append(f"[Attached file: {file_name} (image) saved at: {file_path}]")
        elif att_type == "document":
            file_path = att.get("file_path", "")
            file_name = att.get("file_name", "document")
            mime_type = att.get("mime_type", "")
            doc_references.append(
                f"[Attached file: {file_name} ({mime_type}) saved at: {file_path}]"
            )

    if doc_references and len(parts) == 1:
        return text + "\n\n" + "\n".join(doc_references)

    if doc_references:
        parts.append({"type": "text", "text": "\n".join(doc_references)})

    return parts


def has_image_attachments(attachments: list[dict[str, Any]] | None) -> bool:
    """Return True if any attachment is a renderable image (has data_url)."""
    if not attachments:
        return False
    return any(att.get("type") == "image" and att.get("data_url") for att in attachments)
