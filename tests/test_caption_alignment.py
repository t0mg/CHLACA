import pytest
from piccut.api import align_caption_tokens
from piccut.font_manager import get_font_em_ratio
from piccut.ass_generator import AssSubtitleConfig, generate_ass_content

def test_align_caption_tokens_split_word():
    old_words = [{"word": "somethig", "start": 10.0, "end": 10.8}]
    aligned = align_caption_tokens(["some", "thing"], old_words, 10.0, 10.8)
    assert len(aligned) == 2
    assert aligned[0]["word"] == "some"
    assert aligned[1]["word"] == "thing"
    assert aligned[0]["start"] == 10.0
    assert aligned[1]["end"] == 10.8
    assert aligned[0]["end"] == aligned[1]["start"]

def test_align_caption_tokens_merged_words():
    old_words = [
        {"word": "every", "start": 5.0, "end": 5.4},
        {"word": "day", "start": 5.5, "end": 5.9}
    ]
    aligned = align_caption_tokens(["everyday"], old_words, 5.0, 5.9)
    assert len(aligned) == 1
    assert aligned[0]["word"] == "everyday"
    assert aligned[0]["start"] == 5.0
    assert aligned[0]["end"] == 5.9

def test_align_caption_tokens_moved_word():
    cue0_words = [{"word": "That's", "start": 36.0, "end": 36.3}, {"word": "also", "start": 36.3, "end": 36.6}]
    cue1_words = [{"word": "smaller", "start": 37.0, "end": 37.4}, {"word": "than", "start": 37.4, "end": 37.8}]
    next_cap = {"words": cue1_words, "start": 37.0, "end": 37.8}
    aligned = align_caption_tokens(["That's", "also", "smaller"], cue0_words, 36.0, 36.6, next_cap=next_cap)
    assert len(aligned) == 3
    assert aligned[2]["word"] == "smaller"
    assert aligned[2]["start"] == 37.0
    assert aligned[2]["end"] == 37.4

def test_get_font_em_ratio():
    syne_ratio = get_font_em_ratio("Syne", 800)
    assert 0.5 < syne_ratio < 0.9
    montserrat_ratio = get_font_em_ratio("Montserrat", 800)
    assert 0.5 < montserrat_ratio < 0.9

def test_ass_contiguous_highlight_intervals():
    captions = [{
        "id": 0, "text": "alpha beta", "start": 1.0, "end": 2.5,
        "words": [
            {"word": "alpha", "start": 1.0, "end": 1.3},
            {"word": "beta", "start": 1.8, "end": 2.5}
        ]
    }]
    cfg = AssSubtitleConfig(font_family="Syne", font_size=68, enable_highlight=True)
    ass_text = generate_ass_content(captions, cfg)
    lines = [l for l in ass_text.splitlines() if l.startswith("Dialogue:") and "Default" in l]
    assert len(lines) == 2
    assert "0:00:01.00,0:00:01.80" in lines[0]
    assert "0:00:01.80,0:00:02.50" in lines[1]
