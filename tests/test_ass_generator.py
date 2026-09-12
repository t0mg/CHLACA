"""Unit tests for the ASS subtitle generator."""

import pytest
from piccut.ass_generator import (
    hex_to_ass_color,
    format_ass_time,
    AssSubtitleConfig,
    generate_ass_content
)

def test_hex_to_ass_color():
    # Pure White: #FFFFFF -> &H00FFFFFF&
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF&"
    # Pure Black: #000000 -> &H00000000&
    assert hex_to_ass_color("#000000") == "&H00000000&"
    # Pure Red: #FF0000 -> B=00, G=00, R=FF -> &H000000FF&
    assert hex_to_ass_color("#FF0000") == "&H000000FF&"
    # Pure Blue: #0000FF -> B=FF, G=00, R=00 -> &H00FF0000&
    assert hex_to_ass_color("#0000FF") == "&H00FF0000&"
    # Bright Yellow: #FFFF00 -> B=00, G=FF, R=FF -> &H0000FFFF&
    assert hex_to_ass_color("#FFFF00") == "&H0000FFFF&"
    # With Alpha 100:
    assert hex_to_ass_color("#000000", alpha=100) == "&H64000000&"

def test_format_ass_time():
    assert format_ass_time(0.0) == "0:00:00.00"
    assert format_ass_time(1.5) == "0:00:01.50"
    assert format_ass_time(65.25) == "0:01:05.25"
    assert format_ass_time(3661.12) == "1:01:01.12"

def test_ass_content_generation_with_highlight():
    captions = [
        {
            "id": 0,
            "text": "VIRAL SHORT",
            "start": 1.0,
            "end": 2.0,
            "words": [
                {"word": "VIRAL", "start": 1.0, "end": 1.4},
                {"word": "SHORT", "start": 1.4, "end": 2.0},
            ]
        }
    ]

    cfg = AssSubtitleConfig(
        font_family="Montserrat",
        font_size=75,
        front_color="#FFFFFF",
        back_color="#000000",
        enable_highlight=True,
        highlight_font="Montserrat",
        highlight_size=80,
        highlight_front_color="#FFE600",
        highlight_back_color="#000000",
        vertical_position_pct=72.0
    )

    ass_text = generate_ass_content(captions, cfg)

    # Check ASS structure
    assert "[Script Info]" in ass_text
    assert "PlayResX: 1080" in ass_text
    assert "PlayResY: 1920" in ass_text
    assert "[V4+ Styles]" in ass_text
    assert "Style: Default,Montserrat" in ass_text
    assert ",75," in ass_text
    assert "[Events]" in ass_text

    # Check Dialog lines: 2 lines for 2 words
    lines = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    assert len(lines) == 2
    assert "0:00:01.00,0:00:01.40" in lines[0]
    assert "VIRAL" in lines[0] and "SHORT" in lines[0]

def test_ass_content_generation_without_highlight():
    captions = [
        {
            "id": 0,
            "text": "CLEAN BASE SUBTITLE",
            "start": 1.0,
            "end": 3.0,
            "words": [
                {"word": "CLEAN", "start": 1.0, "end": 1.5},
                {"word": "BASE", "start": 1.5, "end": 2.0},
                {"word": "SUBTITLE", "start": 2.0, "end": 3.0},
            ]
        }
    ]

    cfg = AssSubtitleConfig(
        font_family="Arial",
        font_size=60,
        enable_highlight=False
    )

    ass_text = generate_ass_content(captions, cfg)
    lines = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    # Exactly 1 line for the whole cue when highlight is disabled
    assert len(lines) == 1
    assert "0:00:01.00,0:00:03.00" in lines[0]
    assert "CLEAN BASE SUBTITLE" in lines[0]
    assert "{\\r}" not in lines[0]

def test_ass_content_with_background_box():
    captions = [
        {
            "id": 0,
            "text": "BOXED CAPTION",
            "start": 0.5,
            "end": 2.0,
            "words": [
                {"word": "BOXED", "start": 0.5, "end": 1.2},
                {"word": "CAPTION", "start": 1.2, "end": 2.0},
            ]
        }
    ]

    cfg = AssSubtitleConfig(
        enable_background_box=True,
        background_color="#000000",
        background_alpha=160
    )

    ass_text = generate_ass_content(captions, cfg)
    # Background box uses Layer 0 BgShape vector drawing with rounded bezier corners
    assert "Style: BgShape" in ass_text
    assert "Dialogue: 0" in ass_text and "BgShape" in ass_text and "\\p1" in ass_text and "\\p0" in ass_text
    # Text with word highlight renders cleanly on Layer 1
    assert "Dialogue: 1" in ass_text and "Default" in ass_text
    assert "BOXED" in ass_text and "CAPTION" in ass_text

def test_ass_config_defaults_and_outline_and_font_weight():
    cfg = AssSubtitleConfig()
    assert cfg.outline_width == 0.0
    assert cfg.font_weight == 800

    captions = [
        {
            "id": 0,
            "text": "OUTLINE ZERO TEST",
            "start": 0.0,
            "end": 1.0,
            "words": [
                {"word": "OUTLINE", "start": 0.0, "end": 0.5},
                {"word": "ZERO", "start": 0.5, "end": 1.0}
            ]
        }
    ]

    ass_text = generate_ass_content(captions, cfg)
    # Default outline is 0.0 and shadow is 0.0
    assert ",1,0.0,0.0,2," in ass_text
    # Resolved font name is used (Montserrat ExtraBold with weight 0)
    assert "Montserrat ExtraBold" in ass_text

    # Test non-static font keeps numeric weight
    cfg_custom = AssSubtitleConfig(font_family="CustomUnregisteredFont", font_weight=800)
    ass_custom = generate_ass_content(captions, cfg_custom)
    assert ",800,0,0,0," in ass_custom
    assert "\\b800" in ass_custom
    # No \\3c outline override when outline_width is 0
    assert "\\3c" not in ass_custom

def test_ass_config_highlight_size_delta():
    # Delta specified directly
    cfg1 = AssSubtitleConfig(font_size=68, highlight_size_delta=12)
    assert cfg1.highlight_size == 80
    assert cfg1.highlight_size_delta == 12

    # Negative delta
    cfg2 = AssSubtitleConfig(font_size=68, highlight_size_delta=-10)
    assert cfg2.highlight_size == 58
    assert cfg2.highlight_size_delta == -10

    # Absolute highlight_size specified -> delta computed
    cfg3 = AssSubtitleConfig(font_size=68, highlight_size=72)
    assert cfg3.highlight_size == 72
    assert cfg3.highlight_size_delta == 4

    # Serialization preserves highlight_size_delta
    d = cfg1.to_dict()
    assert d["highlight_size_delta"] == 12
    cfg_restored = AssSubtitleConfig.from_dict(d)
    assert cfg_restored.highlight_size_delta == 12
    assert cfg_restored.highlight_size == 80

def test_ass_empty_cue_omitted_and_duration_extended():
    captions = [
        {
            "id": 0,
            "text": "FIRST LINE",
            "start": 0.0,
            "end": 2.0,
            "words": [
                {"word": "FIRST", "start": 0.0, "end": 1.0},
                {"word": "LINE", "start": 1.0, "end": 2.0},
            ]
        },
        {
            "id": 1,
            "text": "",
            "start": 2.0,
            "end": 4.0,
            "words": []
        },
        {
            "id": 2,
            "text": "THIRD LINE",
            "start": 4.0,
            "end": 6.0,
            "words": [
                {"word": "THIRD", "start": 4.0, "end": 5.0},
                {"word": "LINE", "start": 5.0, "end": 6.0},
            ]
        }
    ]

    cfg = AssSubtitleConfig(enable_background_box=True)
    ass_text = generate_ass_content(captions, cfg)

    # First cue's background box should extend to 4.00 (covering emptied cue 1)
    assert "Dialogue: 0,0:00:00.00,0:00:04.00,BgShape" in ass_text
    # First cue's last word should extend to 4.00
    assert "0:00:01.00,0:00:04.00" in ass_text

    # Emptied cue 1 produces NO Dialogue lines
    lines = [l for l in ass_text.splitlines() if l.startswith("Dialogue:")]
    # Cue 0: 1 BgShape + 2 words = 3 lines
    # Cue 1: 0 lines
    # Cue 2: 1 BgShape + 2 words = 3 lines
    # Total = 6 lines
    assert len(lines) == 6
    assert "Dialogue: 0,0:00:04.00,0:00:06.00,BgShape" in ass_text
