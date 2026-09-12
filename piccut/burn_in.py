"""Video burn-in engine using FFmpeg and libass.
Hardcodes animated word-highlighted subtitles directly into 9:16 vertical videos.
"""

import os
import re
import sys
import json
import logging
import subprocess
from typing import Dict, Any, Optional, Callable
from piccut.font_manager import get_fonts_cache_dir

logger = logging.getLogger(__name__)

def get_subprocess_kwargs() -> Dict[str, Any]:
    """Return kwargs for subprocess to prevent console windows from popping up on Windows."""
    kwargs: Dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo
    return kwargs

def get_video_info(video_path: str) -> Dict[str, Any]:
    """Probe video file with ffprobe to get dimensions, duration, and fps."""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,r_frame_rate,avg_frame_rate",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path
    ]

    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            **get_subprocess_kwargs()
        )
        data = json.loads(res.stdout)
        
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        
        width = 1080
        height = 1920
        duration = 0.0

        if streams:
            width = int(streams[0].get("width", 1080))
            height = int(streams[0].get("height", 1920))
            if "duration" in streams[0] and streams[0]["duration"]:
                duration = float(streams[0]["duration"])

        if duration == 0.0 and "duration" in fmt:
            duration = float(fmt["duration"])

        is_vertical = height > width
        aspect_ratio = width / height if height > 0 else 9 / 16

        return {
            "width": width,
            "height": height,
            "duration": round(duration, 3),
            "is_vertical": is_vertical,
            "aspect_ratio": round(aspect_ratio, 3)
        }
    except Exception as e:
        logger.warning(f"Failed to probe video via ffprobe ({e}). Using defaults (1080x1920).")
        return {
            "width": 1080,
            "height": 1920,
            "duration": 0.0,
            "is_vertical": True,
            "aspect_ratio": 0.562
        }

def escape_ffmpeg_filter_path(path: str) -> str:
    """Properly escape a file path for use inside an FFmpeg filter argument on Windows.
    Colons and backslashes must be escaped.
    """
    # Normalize to forward slashes
    norm = os.path.abspath(path).replace("\\", "/")
    # Escape colon (e.g. C: -> C\\:)
    escaped = norm.replace(":", "\\:")
    # Escape single quotes if any
    escaped = escaped.replace("'", "'\\\\''")
    return escaped

def check_nvenc_available() -> bool:
    """Check if h264_nvenc encoder can actually be initialized on this GPU."""
    try:
        cmd = [
            "ffmpeg",
            "-v", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=64x64:d=0.1",
            "-c:v", "h264_nvenc",
            "-f", "null",
            "-"
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **get_subprocess_kwargs()
        )
        return res.returncode == 0
    except Exception:
        return False

def burn_subtitles(
    input_video: str,
    ass_subtitle_path: str,
    output_video: str,
    use_gpu: bool = True,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    crop_to_vertical: bool = False
) -> str:
    """Burn ASS subtitles directly into video using FFmpeg.
    
    Args:
        input_video: Absolute path to the source video.
        ass_subtitle_path: Absolute path to the generated .ass subtitle file.
        output_video: Destination path for the subtitled video.
        use_gpu: Whether to attempt hardware NVENC encoding.
        progress_callback: Optional callback receiving (status_message, percent_int).
        crop_to_vertical: Whether to crop horizontal video to 9:16 vertical Shorts format.
        
    Returns:
        Absolute path to the final output video.
    """
    if not os.path.isfile(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")
    if not os.path.isfile(ass_subtitle_path):
        raise FileNotFoundError(f"ASS file not found: {ass_subtitle_path}")

    v_info = get_video_info(input_video)
    total_duration = v_info.get("duration", 0.0)

    escaped_ass = escape_ffmpeg_filter_path(ass_subtitle_path)
    fonts_dir = get_fonts_cache_dir()
    if os.path.isdir(fonts_dir):
        escaped_fonts = escape_ffmpeg_filter_path(fonts_dir)
        ass_filter_str = f"ass='{escaped_ass}':fontsdir='{escaped_fonts}'"
    else:
        ass_filter_str = f"ass='{escaped_ass}'"

    if crop_to_vertical and not v_info.get("is_vertical", False):
        # Center-crop horizontal video to 9:16 ratio, scale to 1080x1920, then burn ASS
        vf_filter = f"crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920,{ass_filter_str}"
    else:
        vf_filter = ass_filter_str

    # Select encoder
    gpu_available = check_nvenc_available() if use_gpu else False
    
    if gpu_available:
        logger.info("Using NVIDIA NVENC hardware accelerated encoding (h264_nvenc).")
        encoder_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "21"]
    else:
        logger.info("Using libx264 CPU encoding.")
        encoder_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_video,
        "-vf", vf_filter,
        *encoder_args,
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_video
    ]

    if progress_callback:
        enc_name = "NVIDIA NVENC GPU" if gpu_available else "CPU (x264)"
        progress_callback(f"Starting video rendering with {enc_name}...", 5)

    logger.info(f"Running FFmpeg: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        **get_subprocess_kwargs()
    )

    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

    if process.stdout:
        for line in process.stdout:
            match = time_pattern.search(line)
            if match and total_duration > 0:
                h = int(match.group(1))
                m = int(match.group(2))
                s = float(match.group(3))
                current_time = h * 3600 + m * 60 + s
                pct = min(98, max(5, int((current_time / total_duration) * 95)))
                if progress_callback:
                    progress_callback(f"Rendering subtitles: {int(current_time)}s / {int(total_duration)}s ({pct}%)", pct)

    process.wait()

    if process.returncode != 0:
        # If NVENC failed, retry with libx264 as fallback
        if gpu_available:
            logger.warning("GPU encoding failed. Retrying with CPU libx264...")
            return burn_subtitles(input_video, ass_subtitle_path, output_video, use_gpu=False, progress_callback=progress_callback, crop_to_vertical=crop_to_vertical)
        raise RuntimeError(f"FFmpeg encoding failed with exit code {process.returncode}")

    if not os.path.isfile(output_video) or os.path.getsize(output_video) == 0:
        raise RuntimeError("Output file was not created or is empty.")

    if progress_callback:
        progress_callback("Video export complete!", 100)

    return os.path.abspath(output_video)
