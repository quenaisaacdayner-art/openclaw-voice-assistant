"""Testes da limpeza de markdown pro TTS."""
import pytest
from core.tts import _strip_markdown


class TestStripMarkdown:
    def test_removes_headers(self):
        assert _strip_markdown("# Título") == "Título"
        assert _strip_markdown("## Subtítulo") == "Subtítulo"
        assert _strip_markdown("### Nível 3") == "Nível 3"

    def test_removes_bold(self):
        assert _strip_markdown("texto **negrito** aqui") == "texto negrito aqui"
        assert _strip_markdown("texto __negrito__ aqui") == "texto negrito aqui"

    def test_removes_italic(self):
        assert _strip_markdown("texto *itálico* aqui") == "texto itálico aqui"
        assert _strip_markdown("texto _itálico_ aqui") == "texto itálico aqui"

    def test_removes_bold_italic(self):
        assert _strip_markdown("***importante***") == "importante"

    def test_removes_inline_code(self):
        assert _strip_markdown("use `pip install`") == "use pip install"

    def test_removes_code_blocks(self):
        text = "antes\n```python\nprint('oi')\n```\ndepois"
        result = _strip_markdown(text)
        assert "```" not in result
        assert "antes" in result
        assert "depois" in result

    def test_removes_links_keeps_text(self):
        assert _strip_markdown("[clique aqui](http://example.com)") == "clique aqui"

    def test_removes_images(self):
        result = _strip_markdown("![foto](http://img.jpg)")
        assert "![" not in result
        assert "http" not in result

    def test_removes_blockquotes(self):
        assert _strip_markdown("> citação importante") == "citação importante"

    def test_removes_bullets(self):
        text = "- item 1\n- item 2\n* item 3"
        result = _strip_markdown(text)
        assert "- " not in result
        assert "* " not in result
        assert "item 1" in result

    def test_removes_numbered_lists(self):
        text = "1. primeiro\n2. segundo"
        result = _strip_markdown(text)
        assert "1." not in result
        assert "primeiro" in result

    def test_removes_strikethrough(self):
        assert _strip_markdown("~~deletado~~") == "deletado"

    def test_removes_horizontal_rule(self):
        result = _strip_markdown("texto\n---\nmais texto")
        assert "---" not in result
        assert "texto" in result

    def test_empty_input(self):
        assert _strip_markdown("") == ""
        assert _strip_markdown(None) is None

    def test_plain_text_unchanged(self):
        text = "Isso é texto normal sem formatação."
        assert _strip_markdown(text) == text

    def test_mixed_markdown(self):
        text = "# Título\n\nTexto **negrito** com `código` e [link](url).\n\n- Item 1\n- Item 2"
        result = _strip_markdown(text)
        assert "#" not in result
        assert "**" not in result
        assert "`" not in result
        assert "[link]" not in result
        assert "Título" in result
        assert "negrito" in result
        assert "código" in result
        assert "link" in result
        assert "Item 1" in result
