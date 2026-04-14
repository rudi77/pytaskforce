"""Tests for Markdown-to-Telegram-HTML conversion in outbound sender."""

from taskforce.infrastructure.communication.outbound_senders import (
    _markdown_to_telegram_html,
)


class TestMarkdownToTelegramHtml:
    """Test _markdown_to_telegram_html conversion."""

    def test_plain_text_is_escaped(self):
        assert _markdown_to_telegram_html("Hello <world> & 'friends'") == (
            "Hello &lt;world&gt; &amp; &#x27;friends&#x27;"
        )

    def test_bold_double_asterisk(self):
        result = _markdown_to_telegram_html("This is **bold** text")
        assert "<b>bold</b>" in result

    def test_bold_double_underscore(self):
        result = _markdown_to_telegram_html("This is __bold__ text")
        assert "<b>bold</b>" in result

    def test_italic_single_asterisk(self):
        result = _markdown_to_telegram_html("This is *italic* text")
        assert "<i>italic</i>" in result

    def test_italic_single_underscore(self):
        result = _markdown_to_telegram_html("This is _italic_ text")
        assert "<i>italic</i>" in result

    def test_strikethrough(self):
        result = _markdown_to_telegram_html("This is ~~deleted~~ text")
        assert "<s>deleted</s>" in result

    def test_inline_code(self):
        result = _markdown_to_telegram_html("Use `pip install` here")
        assert "<code>pip install</code>" in result

    def test_code_block(self):
        result = _markdown_to_telegram_html("```python\nprint('hi')\n```")
        assert "<pre><code" in result
        assert "print(&#x27;hi&#x27;)" in result

    def test_code_block_without_language(self):
        result = _markdown_to_telegram_html("```\nsome code\n```")
        assert "<pre><code>some code</code></pre>" in result

    def test_link(self):
        result = _markdown_to_telegram_html("Click [here](https://example.com)")
        assert '<a href="https://example.com">here</a>' in result

    def test_blockquote(self):
        result = _markdown_to_telegram_html("> This is a quote")
        assert "<blockquote>This is a quote</blockquote>" in result

    def test_header_becomes_bold(self):
        result = _markdown_to_telegram_html("## Section Title")
        assert "<b>Section Title</b>" in result

    def test_unordered_list_bullet(self):
        result = _markdown_to_telegram_html("- Item one\n- Item two")
        assert "• Item one" in result
        assert "• Item two" in result

    def test_mixed_formatting(self):
        text = "# Title\n\nSome **bold** and *italic* with `code`."
        result = _markdown_to_telegram_html(text)
        assert "<b>Title</b>" in result
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<code>code</code>" in result

    def test_html_in_input_is_escaped(self):
        """Ensure user-provided HTML tags are escaped, not rendered."""
        result = _markdown_to_telegram_html("Use <script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_multiline_blockquote(self):
        text = "> Line one\n> Line two"
        result = _markdown_to_telegram_html(text)
        assert "<blockquote>" in result
        # Adjacent blockquotes should be merged
        assert result.count("<blockquote>") == 1

    def test_code_block_content_not_formatted(self):
        """Markdown inside code blocks should not be converted."""
        text = "```\n**not bold** and *not italic*\n```"
        result = _markdown_to_telegram_html(text)
        assert "<b>" not in result
        assert "<i>" not in result
