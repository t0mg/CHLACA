"""Unit tests for the smart word chunker."""

import pytest
from piccut.chunker import chunk_words_to_captions

def test_chunking_target_words():
    words = [
        {"word": "This", "start": 0.0, "end": 0.3},
        {"word": "is", "start": 0.3, "end": 0.5},
        {"word": "a", "start": 0.5, "end": 0.7},
        {"word": "great", "start": 0.7, "end": 1.0},
        {"word": "short", "start": 1.0, "end": 1.4},
        {"word": "video", "start": 1.4, "end": 1.8},
    ]

    # Test 2 words per caption
    captions_2 = chunk_words_to_captions(words, target_words_per_caption=2)
    assert len(captions_2) == 3
    assert captions_2[0]["text"] == "This is"
    assert captions_2[1]["text"] == "a great"
    assert captions_2[2]["text"] == "short video"
    assert captions_2[0]["start"] == 0.0
    assert captions_2[2]["end"] == 1.8

    # Test 3 words per caption
    captions_3 = chunk_words_to_captions(words, target_words_per_caption=3)
    assert len(captions_3) == 2
    assert captions_3[0]["text"] == "This is a"
    assert captions_3[1]["text"] == "great short video"

    # Test 1 word per caption
    captions_1 = chunk_words_to_captions(words, target_words_per_caption=1)
    assert len(captions_1) == 6
    assert captions_1[0]["text"] == "This"
    assert captions_1[5]["text"] == "video"

def test_chunking_respects_pauses():
    words = [
        {"word": "Wait", "start": 0.0, "end": 0.4},
        # 0.8s pause here
        {"word": "Look", "start": 1.2, "end": 1.6},
        {"word": "at", "start": 1.6, "end": 1.8},
        {"word": "this", "start": 1.8, "end": 2.1},
    ]

    captions = chunk_words_to_captions(words, target_words_per_caption=3, max_pause_sec=0.5)
    # Even though target is 3 words, "Wait" should split early because of the 0.8s pause!
    assert len(captions) == 2
    assert captions[0]["text"] == "Wait"
    assert captions[1]["text"] == "Look at this"

def test_chunking_respects_punctuation():
    words = [
        {"word": "Stop.", "start": 0.0, "end": 0.3},
        {"word": "Check", "start": 0.35, "end": 0.6},
        {"word": "it", "start": 0.6, "end": 0.8},
    ]

    captions = chunk_words_to_captions(words, target_words_per_caption=3)
    assert len(captions) == 2
    assert captions[0]["text"] == "Stop."
    assert captions[1]["text"] == "Check it"

def test_empty_words():
    captions = chunk_words_to_captions([])
    assert captions == []
