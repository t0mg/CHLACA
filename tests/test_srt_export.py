import os
import pytest
from piccut.ass_generator import format_srt_time, generate_srt_content, AssSubtitleConfig
from piccut.api import AppApi

def test_format_srt_time():
    assert format_srt_time(0.0) == "00:00:00,000"
    assert format_srt_time(1.234) == "00:00:01,234"
    assert format_srt_time(65.5) == "00:01:05,500"
    assert format_srt_time(3661.089) == "01:01:01,089"

def test_generate_srt_content():
    captions = [
        {
            "id": 0,
            "start": 0.5,
            "end": 1.75,
            "text": "Hello world today",
            "words": [
                {"word": "Hello", "start": 0.5, "end": 0.9},
                {"word": "world", "start": 0.9, "end": 1.3},
                {"word": "today", "start": 1.3, "end": 1.75}
            ]
        },
        {
            "id": 1,
            "start": 2.0,
            "end": 3.2,
            "text": "This is piccut",
            "words": [
                {"word": "This", "start": 2.0, "end": 2.3},
                {"word": "is", "start": 2.3, "end": 2.5},
                {"word": "piccut", "start": 2.5, "end": 3.2}
            ]
        }
    ]

    srt_str = generate_srt_content(captions)
    assert "1\n00:00:00,500 --> 00:00:01,750\nHello world today" in srt_str
    assert "2\n00:00:02,000 --> 00:00:03,200\nThis is piccut" in srt_str

def test_api_export_subtitles_file(tmp_path):
    api = AppApi()
    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"dummy")

    api.current_video_path = str(dummy_video)
    api.captions = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "Test Caption", "words": [{"word": "Test", "start": 0.0, "end": 0.5}, {"word": "Caption", "start": 0.5, "end": 1.0}]}
    ]

    # Export SRT
    res_srt = api.export_subtitles_file("srt")
    assert res_srt["success"] is True
    assert os.path.isfile(res_srt["output_path"])
    with open(res_srt["output_path"], "r", encoding="utf-8") as f:
        content = f.read()
        assert "Test Caption" in content
        assert "00:00:00,000 --> 00:00:01,000" in content

    # Export ASS
    res_ass = api.export_subtitles_file("ass")
    assert res_ass["success"] is True
    assert os.path.isfile(res_ass["output_path"])
    with open(res_ass["output_path"], "r", encoding="utf-8") as f:
        ass_text = f.read()
        assert "[Script Info]" in ass_text
        assert "Test Caption" in ass_text or "Test" in ass_text

def test_api_crop_to_vertical_resolution(tmp_path):
    api = AppApi()
    # Mock horizontal video info (1920x1080)
    api.video_info = {
        "width": 1920,
        "height": 1080,
        "duration": 5.0,
        "is_vertical": False,
        "aspect_ratio": 1.778
    }

    # When crop_to_vertical is True (default)
    api.set_crop_to_vertical(True)
    assert api.crop_to_vertical is True
    assert api.style_config.play_res_x == 1080
    assert api.style_config.play_res_y == 1920

    # When crop_to_vertical is False (native aspect ratio)
    api.set_crop_to_vertical(False)
    assert api.crop_to_vertical is False
    assert api.style_config.play_res_x == 1920
    assert api.style_config.play_res_y == 1080

def test_srt_empty_cue_omitted_and_extended():
    captions = [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "First chunk"},
        {"id": 1, "start": 2.0, "end": 4.0, "text": ""},
        {"id": 2, "start": 4.0, "end": 6.0, "text": "Third chunk"}
    ]
    srt_text = generate_srt_content(captions)
    assert "First chunk" in srt_text
    assert "00:00:00,000 --> 00:00:04,000" in srt_text
    assert "Third chunk" in srt_text
    assert "00:00:04,000 --> 00:00:06,000" in srt_text
    assert "2\n00:00:04,000" in srt_text  # Re-indexed properly to 2 blocks

def test_api_update_caption_empty_extends_duration():
    api = AppApi()
    api.captions = [
        {
            "id": 0,
            "start": 0.0,
            "end": 2.0,
            "text": "First cue",
            "words": [{"word": "First", "start": 0.0, "end": 1.0}, {"word": "cue", "start": 1.0, "end": 2.0}]
        },
        {
            "id": 1,
            "start": 2.0,
            "end": 4.0,
            "text": "Second cue",
            "words": [{"word": "Second", "start": 2.0, "end": 3.0}, {"word": "cue", "start": 3.0, "end": 4.0}]
        }
    ]

    # Empty the second cue
    res = api.update_caption(1, "")
    assert res["success"] is True
    # First cue's end should be extended to 4.0
    assert api.captions[0]["end"] == 4.0
    # Second cue's words should be cleared
    assert api.captions[1]["words"] == []
    assert api.captions[1]["text"] == ""

    # Restore the second cue
    res2 = api.update_caption(1, "Second restored")
    assert res2["success"] is True
    # First cue's end should be restored back to 2.0
    assert api.captions[0]["end"] == 2.0
    assert len(api.captions[1]["words"]) == 2

