"""Performance and caching tests for AvatarEngine event processing."""

import pytest
import time
from unittest.mock import MagicMock
from avatar_engine import AvatarEngine
from avatar_engine.events import ThinkingEvent, ThinkingPhase

def test_thinking_event_caching():
    """Verify that AvatarEngine caches thinking subject and phase."""
    engine = AvatarEngine()
    
    # Mock emit to capture events
    engine.emit = MagicMock()
    
    # Simulate first chunk of a thinking block
    event1 = {
        "type": "thinking",
        "thought": "I am **Analyzing imports** to understand...",
        "block_id": "block1",
        "is_start": True
    }
    
    engine._process_event(event1)
    
    # Verify first event
    assert engine.emit.call_count == 1
    emitted_event1 = engine.emit.call_args[0][0]
    assert isinstance(emitted_event1, ThinkingEvent)
    assert emitted_event1.subject == "Analyzing imports"
    assert emitted_event1.phase == ThinkingPhase.ANALYZING
    
    # Check engine cache
    assert engine._current_thinking_block_id == "block1"
    assert engine._current_thinking_subject == "Analyzing imports"
    assert engine._current_thinking_phase == ThinkingPhase.ANALYZING
    
    # Simulate second chunk of the same block
    event2 = {
        "type": "thinking",
        "thought": "I am **Analyzing imports** to understand dependencies in the codebase.",
        "block_id": "block1",
        "is_start": False
    }
    
    # Mock extract_bold_subject and classify_thinking to verify they are NOT called again
    with MagicMock() as mock_extract, MagicMock() as mock_classify:
        # We need to patch them in the module where they are used (engine.py)
        import avatar_engine.engine as engine_module
        original_extract = engine_module.extract_bold_subject
        original_classify = engine_module.classify_thinking
        
        engine_module.extract_bold_subject = mock_extract
        engine_module.classify_thinking = mock_classify
        
        try:
            engine._process_event(event2)
        finally:
            # Restore
            engine_module.extract_bold_subject = original_extract
            engine_module.classify_thinking = original_classify
            
    # Verify second event
    assert engine.emit.call_count == 2
    emitted_event2 = engine.emit.call_args[0][0]
    assert emitted_event2.subject == "Analyzing imports"
    assert emitted_event2.phase == ThinkingPhase.ANALYZING
    
    # Verify cache was used (mock functions should NOT have been called)
    assert mock_extract.call_count == 0
    # Note: classify_thinking might be called if phase was GENERAL, 
    # but here it was ANALYZING, so it should be skipped.
    assert mock_classify.call_count == 0

def test_thinking_event_new_block_resets_cache():
    """Verify that cache is reset for a new thinking block."""
    engine = AvatarEngine()
    engine.emit = MagicMock()
    
    # Block 1
    engine._process_event({
        "type": "thinking",
        "thought": "I am **Analyzing imports**",
        "block_id": "block1"
    })
    assert engine._current_thinking_subject == "Analyzing imports"
    
    # Block 2
    engine._process_event({
        "type": "thinking",
        "thought": "I am **Planning implementation**",
        "block_id": "block2"
    })
    
    assert engine._current_thinking_block_id == "block2"
    assert engine._current_thinking_subject == "Planning implementation"
    assert engine._current_thinking_phase == ThinkingPhase.PLANNING

def test_performance_improvement():
    """Measure performance improvement with caching."""
    engine = AvatarEngine()
    engine.emit = MagicMock()
    
    # Large thinking block
    subject = "Analyzing complex dependencies in a very large codebase"
    base_thought = f"I am **{subject}** " + "and " * 1000
    
    num_events = 100
    
    start_time = time.time()
    for i in range(num_events):
        thought = base_thought + str(i)
        engine._process_event({
            "type": "thinking",
            "thought": thought,
            "block_id": "perf_block"
        })
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"\nProcessed {num_events} high-frequency events in {duration:.4f}s")
    
    # With caching, this should be very fast regardless of text length
    # Each call should be O(1) after the first one.
    assert duration < 0.5  # Should be much faster than 0.5s on any modern machine
