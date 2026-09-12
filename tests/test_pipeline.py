"""End-to-end integration test of the entire PicCut pipeline:
Video -> faster-whisper ASR -> Word Chunking -> ASS Subtitle Generation -> FFmpeg Burn-In.
"""

import os
import pytest
from piccut.transcriber import Transcriber
from piccut.chunker import chunk_words_to_captions
from piccut.ass_generator import AssSubtitleConfig, generate_ass_content
from piccut.burn_in import burn_subtitles, get_video_info

@pytest.mark.timeout(60)
def test_full_pipeline_end_to_end(tmp_path):
    video_path = "tests/fixtures/test_vertical_short.mp4"
    assert os.path.isfile(video_path), "Test input video must exist"

    # Step 1: Probe video
    info = get_video_info(video_path)
    assert info["is_vertical"] is True
    assert info["width"] == 1080
    assert info["height"] == 1920
    assert info["duration"] > 5.0

    # Step 2: On-device Transcription with word timestamps
    # Using tiny model for fast CI/test execution
    transcriber = Transcriber(model_size="tiny", device="cpu", compute_type="int8")
    result = transcriber.transcribe(video_path, language="en")

    words = result["words"]
    assert len(words) > 0, "Should transcribe words from speech"
    print(f"Transcribed {len(words)} words: {[w['word'] for w in words]}")

    for w in words:
        assert "word" in w
        assert "start" in w
        assert "end" in w
        assert w["end"] >= w["start"]

    # Step 3: Word Chunking
    captions = chunk_words_to_captions(words, target_words_per_caption=3)
    assert len(captions) > 0
    for cap in captions:
        assert len(cap["words"]) <= 3
        assert cap["end"] >= cap["start"]

    # Step 4: ASS Generation with animated styling
    cfg = AssSubtitleConfig(
        font_family="Montserrat",
        font_size=75,
        front_color="#FFFFFF",
        back_color="#000000",
        highlight_front_color="#FFE600",
        highlight_back_color="#000000",
        vertical_position_pct=72.0
    )
    ass_text = generate_ass_content(captions, cfg)
    assert "[Script Info]" in ass_text
    assert "[Events]" in ass_text

    ass_path = str(tmp_path / "test_pipeline_output.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_text)

    # Step 5: Direct FFmpeg Burn-In
    out_video = str(tmp_path / "test_pipeline_burned.mp4")

    final_path = burn_subtitles(video_path, ass_path, out_video, use_gpu=False)
    assert os.path.isfile(final_path)
    assert os.path.getsize(final_path) > 10000

    # Verify burned video
    burned_info = get_video_info(final_path)
    assert burned_info["width"] == 1080
    assert burned_info["height"] == 1920
    assert burned_info["duration"] > 5.0
