"""Tests for multimodal attachment support in bridges."""

import base64
import json
from pathlib import Path

import pytest

from avatar_engine.types import Attachment


class TestClaudeMultimodal:
    """Test Claude bridge _format_user_message with attachments."""

    def _make_bridge(self):
        from avatar_engine.bridges.claude import ClaudeBridge
        return ClaudeBridge(executable="claude", working_dir="/tmp")

    def _make_attachment(self, tmp_path, filename, data, mime_type):
        path = tmp_path / filename
        path.write_bytes(data)
        return Attachment(path=path, mime_type=mime_type, filename=filename, size=len(data))

    def test_text_only_no_attachments(self, tmp_path):
        bridge = self._make_bridge()
        result = json.loads(bridge._format_user_message("hello"))
        content = result["message"]["content"]
        assert len(content) == 1
        assert content[0] == {"type": "text", "text": "hello"}

    def test_image_attachment(self, tmp_path):
        bridge = self._make_bridge()
        img_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        att = self._make_attachment(tmp_path, "photo.png", img_data, "image/png")

        result = json.loads(bridge._format_user_message("describe this", attachments=[att]))
        content = result["message"]["content"]

        assert len(content) == 2
        # Image block first
        assert content[0]["type"] == "image"
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/png"
        assert base64.b64decode(content[0]["source"]["data"]) == img_data
        # Text block last
        assert content[1] == {"type": "text", "text": "describe this"}

    def test_pdf_attachment(self, tmp_path):
        bridge = self._make_bridge()
        pdf_data = b"%PDF-1.4" + b"\x00" * 100
        att = self._make_attachment(tmp_path, "book.pdf", pdf_data, "application/pdf")

        result = json.loads(bridge._format_user_message("analyze", attachments=[att]))
        content = result["message"]["content"]

        assert len(content) == 2
        assert content[0]["type"] == "document"
        assert content[0]["source"]["media_type"] == "application/pdf"
        assert content[0]["title"] == "book.pdf"
        assert base64.b64decode(content[0]["source"]["data"]) == pdf_data
        assert content[1] == {"type": "text", "text": "analyze"}

    def test_multiple_attachments(self, tmp_path):
        bridge = self._make_bridge()
        img = self._make_attachment(tmp_path, "a.jpg", b"\xff\xd8\xff", "image/jpeg")
        pdf = self._make_attachment(tmp_path, "b.pdf", b"%PDF", "application/pdf")

        result = json.loads(bridge._format_user_message("both", attachments=[img, pdf]))
        content = result["message"]["content"]

        assert len(content) == 3
        assert content[0]["type"] == "image"
        assert content[1]["type"] == "document"
        assert content[2]["type"] == "text"

    def test_unsupported_mime_type_skipped(self, tmp_path):
        bridge = self._make_bridge()
        att = self._make_attachment(tmp_path, "data.csv", b"a,b,c", "text/csv")

        result = json.loads(bridge._format_user_message("parse", attachments=[att]))
        content = result["message"]["content"]
        # CSV is not image or PDF, so only text block
        assert len(content) == 1
        assert content[0]["type"] == "text"

    def test_session_id_preserved(self, tmp_path):
        bridge = self._make_bridge()
        bridge.session_id = "test-session-123"
        att = self._make_attachment(tmp_path, "x.png", b"\x89PNG", "image/png")

        result = json.loads(bridge._format_user_message("hi", attachments=[att]))
        assert result["session_id"] == "test-session-123"

    def test_none_attachments_same_as_no_attachments(self, tmp_path):
        bridge = self._make_bridge()
        a = json.loads(bridge._format_user_message("hello"))
        b = json.loads(bridge._format_user_message("hello", attachments=None))
        c = json.loads(bridge._format_user_message("hello", attachments=[]))
        assert a["message"]["content"] == b["message"]["content"] == c["message"]["content"]


class TestGeminiMultimodal:
    """Test Gemini bridge _build_prompt_blocks helper."""

    def _make_attachment(self, tmp_path, filename, data, mime_type):
        path = tmp_path / filename
        path.write_bytes(data)
        return Attachment(path=path, mime_type=mime_type, filename=filename, size=len(data))

    def test_text_only(self):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        blocks = _build_prompt_blocks("hello")
        assert len(blocks) == 1
        assert blocks[0].type == "text"
        assert blocks[0].text == "hello"

    def test_image_attachment(self, tmp_path):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        img_data = b"\x89PNG" + b"\x00" * 20
        att = self._make_attachment(tmp_path, "photo.png", img_data, "image/png")

        blocks = _build_prompt_blocks("describe", [att])
        assert len(blocks) == 2
        assert blocks[0].type == "image"
        assert blocks[0].mime_type == "image/png"
        assert base64.b64decode(blocks[0].data) == img_data
        assert blocks[1].type == "text"
        assert blocks[1].text == "describe"

    def test_pdf_as_embedded_resource(self, tmp_path):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        pdf_data = b"%PDF-1.4"
        att = self._make_attachment(tmp_path, "doc.pdf", pdf_data, "application/pdf")

        blocks = _build_prompt_blocks("analyze", [att])
        assert len(blocks) == 2
        assert blocks[0].type == "resource"
        assert blocks[0].resource.mime_type == "application/pdf"
        assert base64.b64decode(blocks[0].resource.blob) == pdf_data
        assert blocks[1].type == "text"

    def test_audio_attachment(self, tmp_path):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        audio_data = b"\xff\xfb\x90" + b"\x00" * 30
        att = self._make_attachment(tmp_path, "clip.mp3", audio_data, "audio/mp3")

        blocks = _build_prompt_blocks("transcribe", [att])
        assert len(blocks) == 2
        assert blocks[0].type == "audio"
        assert blocks[0].mime_type == "audio/mp3"
        assert blocks[1].type == "text"

    def test_none_attachments(self):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        blocks_none = _build_prompt_blocks("hi", None)
        blocks_empty = _build_prompt_blocks("hi", [])
        blocks_bare = _build_prompt_blocks("hi")
        assert len(blocks_none) == len(blocks_empty) == len(blocks_bare) == 1

    def test_multiple_attachments(self, tmp_path):
        from avatar_engine.bridges.gemini import _build_prompt_blocks
        img = self._make_attachment(tmp_path, "a.jpg", b"\xff\xd8", "image/jpeg")
        pdf = self._make_attachment(tmp_path, "b.pdf", b"%PDF", "application/pdf")
        audio = self._make_attachment(tmp_path, "c.mp3", b"\xff\xfb", "audio/mp3")

        blocks = _build_prompt_blocks("all", [img, pdf, audio])
        assert len(blocks) == 4  # 3 attachments + 1 text
        types = [b.type for b in blocks]
        assert types == ["image", "resource", "audio", "text"]
