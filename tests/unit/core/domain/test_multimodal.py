"""Tests for the shared multimodal-content helper."""

from __future__ import annotations

from taskforce.core.domain.multimodal import (
    build_multimodal_content,
    has_image_attachments,
)


class TestBuildMultimodalContent:
    def test_no_attachments_returns_plain_string(self) -> None:
        assert build_multimodal_content("hello", None) == "hello"
        assert build_multimodal_content("hello", []) == "hello"

    def test_single_image_attachment_yields_content_blocks(self) -> None:
        data_url = "data:image/jpeg;base64,AAAA"
        result = build_multimodal_content("caption", [{"type": "image", "data_url": data_url}])

        assert isinstance(result, list)
        assert result[0] == {"type": "text", "text": "caption"}
        assert {"type": "image_url", "image_url": {"url": data_url}} in result

    def test_document_only_returns_enriched_string(self) -> None:
        result = build_multimodal_content(
            "look at this",
            [
                {
                    "type": "document",
                    "file_path": "/tmp/foo.pdf",
                    "file_name": "foo.pdf",
                    "mime_type": "application/pdf",
                }
            ],
        )

        assert isinstance(result, str)
        assert "look at this" in result
        assert "/tmp/foo.pdf" in result
        assert "foo.pdf" in result
        assert "application/pdf" in result

    def test_image_with_file_path_adds_doc_reference_block(self) -> None:
        result = build_multimodal_content(
            "see this",
            [
                {
                    "type": "image",
                    "data_url": "data:image/png;base64,BBBB",
                    "file_path": "/tmp/x.png",
                    "file_name": "x.png",
                }
            ],
        )

        assert isinstance(result, list)
        text_parts = [p["text"] for p in result if p.get("type") == "text"]
        # First text part is the caption, subsequent text parts mention the file path.
        assert text_parts[0] == "see this"
        assert any("/tmp/x.png" in t for t in text_parts[1:])

    def test_image_attachment_missing_data_url_is_skipped(self) -> None:
        """An image entry without data_url is invalid; should not crash and
        should not produce an image_url block."""
        result = build_multimodal_content(
            "caption",
            [{"type": "image"}],
        )
        # No data_url -> no image_url block. Either plain string (if no doc
        # references) or a list without image blocks.
        if isinstance(result, list):
            assert not any(p.get("type") == "image_url" for p in result)
        else:
            assert result == "caption"


class TestHasImageAttachments:
    def test_none_returns_false(self) -> None:
        assert has_image_attachments(None) is False

    def test_empty_returns_false(self) -> None:
        assert has_image_attachments([]) is False

    def test_document_only_returns_false(self) -> None:
        assert has_image_attachments([{"type": "document", "file_path": "/tmp/x.pdf"}]) is False

    def test_image_without_data_url_returns_false(self) -> None:
        assert has_image_attachments([{"type": "image"}]) is False

    def test_image_with_data_url_returns_true(self) -> None:
        assert (
            has_image_attachments([{"type": "image", "data_url": "data:image/png;base64,AAAA"}])
            is True
        )
