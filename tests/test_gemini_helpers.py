"""Tests for Gemini bridge helper functions."""

import pytest
from avatar_engine.bridges.gemini import (
    _extract_thinking_from_update,
    _extract_text_from_update,
    _extract_text_from_result,
    _is_thinking_block,
)


class MockContentBlock:
    """Mock content block for testing."""
    def __init__(self, text=None, type_=None, thinking=None):
        if text is not None:
            self.text = text
        if type_ is not None:
            self.type = type_
        if thinking is not None:
            self.thinking = thinking


class MockUpdate:
    """Mock ACP update for testing."""
    def __init__(self, thinking=None, content=None, agent_message=None):
        if thinking is not None:
            self.thinking = thinking
        if content is not None:
            self.content = content
        if agent_message is not None:
            self.agent_message = agent_message


class MockAgentMessage:
    """Mock agent message for testing."""
    def __init__(self, thinking=None, content=None):
        if thinking is not None:
            self.thinking = thinking
        if content is not None:
            self.content = content


class TestExtractThinkingFromUpdate:
    """Tests for _extract_thinking_from_update function."""

    def test_extract_thinking_from_attribute_string(self):
        """Should extract thinking from direct string attribute."""
        update = MockUpdate(thinking="Let me think about this...")
        result = _extract_thinking_from_update(update)
        assert result == "Let me think about this..."

    def test_extract_thinking_from_attribute_text(self):
        """Should extract thinking from thinking.text attribute."""
        thinking_obj = MockContentBlock(text="Analyzing the problem...")
        update = MockUpdate(thinking=thinking_obj)
        result = _extract_thinking_from_update(update)
        assert result == "Analyzing the problem..."

    def test_extract_thinking_from_content_block(self):
        """Should extract thinking from content block with type='thinking'."""
        block = MockContentBlock(text="Step 1: Consider...", type_="thinking")
        update = MockUpdate(content=[block])
        result = _extract_thinking_from_update(update)
        assert result == "Step 1: Consider..."

    def test_extract_thinking_from_agent_message(self):
        """Should extract thinking from agent_message.thinking."""
        msg = MockAgentMessage(thinking="Internal reasoning...")
        update = MockUpdate(agent_message=msg)
        result = _extract_thinking_from_update(update)
        assert result == "Internal reasoning..."

    def test_extract_thinking_from_dict(self):
        """Should extract thinking from dict-style update."""
        update = {"thinking": "Processing query..."}
        result = _extract_thinking_from_update(update)
        assert result == "Processing query..."

    def test_extract_thinking_from_dict_agent_message(self):
        """Should extract thinking from dict with agentMessage."""
        update = {"agentMessage": {"thinking": "Evaluating options..."}}
        result = _extract_thinking_from_update(update)
        assert result == "Evaluating options..."

    def test_extract_thinking_from_dict_content_block(self):
        """Should extract thinking from dict content block."""
        update = {
            "agentMessage": {
                "content": [{"type": "thinking", "text": "First, let me..."}]
            }
        }
        result = _extract_thinking_from_update(update)
        assert result == "First, let me..."

    def test_no_thinking_returns_none(self):
        """Should return None when no thinking content found."""
        update = MockUpdate(content=[MockContentBlock(text="Regular text")])
        result = _extract_thinking_from_update(update)
        assert result is None

    def test_empty_thinking_returns_none(self):
        """Should return None for empty thinking."""
        update = MockUpdate(thinking="")
        result = _extract_thinking_from_update(update)
        assert result is None


class TestExtractTextFromUpdate:
    """Tests for _extract_text_from_update function."""

    def test_extract_text_from_content_text(self):
        """Should extract text from content.text."""
        content = MockContentBlock(text="Hello world")
        update = MockUpdate(content=content)
        result = _extract_text_from_update(update)
        assert result == "Hello world"

    def test_extract_text_from_content_list(self):
        """Should extract text from list of content blocks."""
        blocks = [
            MockContentBlock(text="Part 1"),
            MockContentBlock(text=" Part 2"),
        ]
        update = MockUpdate(content=blocks)
        result = _extract_text_from_update(update)
        assert result == "Part 1 Part 2"

    def test_extract_text_from_agent_message(self):
        """Should extract text from agent_message.content."""
        content = [MockContentBlock(text="Response text")]
        msg = MockAgentMessage(content=content)
        update = MockUpdate(agent_message=msg)
        result = _extract_text_from_update(update)
        assert result == "Response text"

    def test_extract_text_from_dict(self):
        """Should extract text from dict-style update."""
        update = {
            "agentMessage": {
                "content": [{"text": "Dict response"}]
            }
        }
        result = _extract_text_from_update(update)
        assert result == "Dict response"

    def test_no_text_returns_none(self):
        """Should return None when no text content found."""
        update = MockUpdate()
        result = _extract_text_from_update(update)
        assert result is None


class TestExtractTextFromResult:
    """Tests for _extract_text_from_result function."""

    def test_extract_from_content_text(self):
        """Should extract text from result.content.text."""
        content = MockContentBlock(text="Final answer")
        result_obj = MockUpdate(content=content)
        result = _extract_text_from_result(result_obj)
        assert result == "Final answer"

    def test_extract_from_content_list(self):
        """Should extract text from list of content blocks."""
        blocks = [
            MockContentBlock(text="Answer "),
            MockContentBlock(text="part 2"),
        ]
        result_obj = MockUpdate(content=blocks)
        result = _extract_text_from_result(result_obj)
        assert result == "Answer part 2"

    def test_extract_from_dict_content(self):
        """Should extract text from dict-style result."""
        result_obj = MockUpdate(content=[{"text": "Dict result"}])
        result = _extract_text_from_result(result_obj)
        assert result == "Dict result"

    def test_no_content_returns_empty(self):
        """Should return empty string when no content."""
        result_obj = MockUpdate()
        result = _extract_text_from_result(result_obj)
        assert result == ""

    def test_thinking_blocks_excluded_from_result(self):
        """Thinking blocks should not appear in text result."""
        blocks = [
            MockContentBlock(text="I need to analyze...", type_="thinking"),
            MockContentBlock(text="Here is the answer."),
        ]
        result_obj = MockUpdate(content=blocks)
        result = _extract_text_from_result(result_obj)
        assert result == "Here is the answer."
        assert "analyze" not in result


class TestIsThinkingBlock:
    """Tests for _is_thinking_block helper."""

    def test_type_thinking(self):
        block = MockContentBlock(text="reasoning", type_="thinking")
        assert _is_thinking_block(block) is True

    def test_type_text(self):
        block = MockContentBlock(text="response", type_="text")
        assert _is_thinking_block(block) is False

    def test_thinking_attribute(self):
        block = MockContentBlock(thinking="some thought")
        assert _is_thinking_block(block) is True

    def test_plain_text_block(self):
        block = MockContentBlock(text="just text")
        assert _is_thinking_block(block) is False

    def test_dict_thinking(self):
        assert _is_thinking_block({"type": "thinking", "text": "..."}) is True

    def test_dict_text(self):
        assert _is_thinking_block({"type": "text", "text": "..."}) is False


class TestThinkingExcludedFromText:
    """Verify thinking content blocks are NOT extracted as text."""

    def test_update_with_mixed_content_blocks(self):
        """Mixed thinking + text blocks: only text should be extracted."""
        blocks = [
            MockContentBlock(text="Let me think...", type_="thinking"),
            MockContentBlock(text="The answer is 42."),
        ]
        update = MockUpdate(content=blocks)
        result = _extract_text_from_update(update)
        assert result == "The answer is 42."

    def test_update_only_thinking_returns_none(self):
        """Update with only thinking blocks should return None."""
        blocks = [
            MockContentBlock(text="Analyzing problem...", type_="thinking"),
        ]
        update = MockUpdate(content=blocks)
        result = _extract_text_from_update(update)
        assert result is None

    def test_agent_message_with_thinking_blocks(self):
        """Thinking blocks in agent_message should be excluded."""
        blocks = [
            MockContentBlock(text="Planning response...", type_="thinking"),
            MockContentBlock(text="Here is my response."),
        ]
        msg = MockAgentMessage(content=blocks)
        update = MockUpdate(agent_message=msg)
        result = _extract_text_from_update(update)
        assert result == "Here is my response."

    def test_dict_update_thinking_excluded(self):
        """Dict-style thinking blocks should be excluded."""
        update = {
            "agentMessage": {
                "content": [
                    {"type": "thinking", "text": "Let me consider..."},
                    {"type": "text", "text": "Final answer."},
                ]
            }
        }
        result = _extract_text_from_update(update)
        assert result == "Final answer."

    def test_single_thinking_content_block(self):
        """Single thinking content block should return None."""
        block = MockContentBlock(text="Internal thought", type_="thinking")
        update = MockUpdate(content=block)
        result = _extract_text_from_update(update)
        assert result is None

    def test_single_text_content_block(self):
        """Single non-thinking content block should return text."""
        block = MockContentBlock(text="Regular response")
        update = MockUpdate(content=block)
        result = _extract_text_from_update(update)
        assert result == "Regular response"
