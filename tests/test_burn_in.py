"""Unit tests for the FFmpeg burn-in module."""

import os
import pytest
from piccut.burn_in import get_video_info, escape_ffmpeg_filter_path

def test_escape_ffmpeg_filter_path():
    p = r"C:\Users\tomgr\dev\piccut\subtitles.ass"
    escaped = escape_ffmpeg_filter_path(p)
    # Check that directory separators are converted to forward slashes
    # and colon is escaped (e.g. C\:/)
    assert "C\\:/" in escaped
    assert "/dev/piccut/subtitles.ass" in escaped

def test_probe_sample_video():
    sample_path = "tests/fixtures/test_vertical_short.mp4"
    if os.path.exists(sample_path):
        info = get_video_info(sample_path)
        assert info["width"] == 1080
        assert info["height"] == 1920
        assert info["is_vertical"] is True
        assert info["duration"] > 0

def test_burn_horizontal_video_crop(tmp_path):
    import subprocess
    from piccut.burn_in import burn_subtitles
    from piccut.ass_generator import AssSubtitleConfig, generate_ass_content

    # Generate a 1-second 1920x1080 horizontal test video
    h_video = str(tmp_path / "test_16_9.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=1",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1",
        "-c:v", "libx264", "-c:a", "aac", h_video
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ass_file = str(tmp_path / "test.ass")
    captions = [{"id": 0, "start": 0.1, "end": 0.9, "text": "Horizontal Crop Test", "words": [{"word": "Horizontal", "start": 0.1, "end": 0.5}, {"word": "Crop", "start": 0.5, "end": 0.9}]}]
    
    # 1. Test crop_to_vertical=True -> exports 1080x1920 vertical video
    config_vertical = AssSubtitleConfig(play_res_x=1080, play_res_y=1920)
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write(generate_ass_content(captions, config_vertical))
        
    out_cropped = str(tmp_path / "out_cropped_9_16.mp4")
    res_cropped = burn_subtitles(h_video, ass_file, out_cropped, use_gpu=False, crop_to_vertical=True)
    assert os.path.isfile(res_cropped)
    info_cropped = get_video_info(res_cropped)
    assert info_cropped["width"] == 1080
    assert info_cropped["height"] == 1920
    assert info_cropped["is_vertical"] is True

    # 2. Test crop_to_vertical=False -> exports native 1920x1080 horizontal video
    out_native = str(tmp_path / "out_native_16_9.mp4")
    res_native = burn_subtitles(h_video, ass_file, out_native, use_gpu=False, crop_to_vertical=False)
    assert os.path.isfile(res_native)
    info_native = get_video_info(res_native)
    assert info_native["width"] == 1920
    assert info_native["height"] == 1080
    assert info_native["is_vertical"] is False

