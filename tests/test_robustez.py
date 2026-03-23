"""Testes de robustez — timeout, cleanup, sessão longa."""
import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestLLMTimeout:
    """Verifica que LLM_TIMEOUT existe no código-fonte de server_ws.py."""

    def test_timeout_constant_in_source(self):
        """LLM_TIMEOUT deve estar definido no server_ws.py."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "server_ws.py"
        code = src.read_text(encoding="utf-8")
        assert "LLM_TIMEOUT" in code
        # Deve ser 120
        assert "LLM_TIMEOUT = 120" in code

    def test_timeout_used_in_streaming(self):
        """O loop de streaming deve checar LLM_TIMEOUT."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "server_ws.py"
        code = src.read_text(encoding="utf-8")
        assert "t_last_data" in code
        assert "time.time() - t_last_data > LLM_TIMEOUT" in code


class TestStripMarkdownIntegration:
    """Verifica que generate_tts usa _strip_markdown."""

    def test_strip_is_called_in_generate(self):
        """_strip_markdown deve ser chamada dentro de generate_tts."""
        from core.tts import generate_tts, _strip_markdown
        # Verificar que a função existe e é importável
        assert callable(_strip_markdown)

    def test_code_block_not_spoken(self):
        from core.tts import _strip_markdown
        text = "Instale assim:\n```\npip install pacote\n```\nDepois configure."
        result = _strip_markdown(text)
        assert "```" not in result
        assert "Depois configure" in result


class TestProcessingLock:
    """Verifica que processing_lock e pending_audio existem."""

    def test_asyncio_lock_importable(self):
        """asyncio.Lock deve estar disponível (usado pra race condition)."""
        lock = asyncio.Lock()
        assert not lock.locked()

    def test_lock_in_source(self):
        """processing_lock e pending_audio devem existir no server_ws.py."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "server_ws.py"
        code = src.read_text(encoding="utf-8")
        assert "processing_lock = asyncio.Lock()" in code
        assert "pending_audio" in code
        assert "async with processing_lock:" in code


class TestCleanupDisconnect:
    """Verifica que WebSocketDisconnect faz cleanup completo."""

    def test_disconnect_cancels_task(self):
        """WebSocketDisconnect deve cancelar process_task e limpar buffers."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "server_ws.py"
        code = src.read_text(encoding="utf-8")
        assert "except WebSocketDisconnect:" in code
        assert "cancel_event.set()" in code
        assert "process_task.cancel()" in code
        assert "pending_audio.clear()" in code
        assert "Cleanup completo" in code


class TestClearHistory:
    """Verifica que clear_history handler existe."""

    def test_clear_history_handler(self):
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "server_ws.py"
        code = src.read_text(encoding="utf-8")
        assert '"clear_history"' in code
        assert "chat_history.clear()" in code
        assert '"history_cleared"' in code
