"""Desktop API bridge between pywebview and the Python video/ASR backend.
"""

import os
import sys
import json
import difflib
import logging
import threading
from typing import Dict, Any, Optional, List

from piccut.transcriber import Transcriber, AVAILABLE_MODELS, get_available_devices
from piccut.chunker import chunk_words_to_captions
from piccut.ass_generator import AssSubtitleConfig, generate_ass_content, generate_srt_content
from piccut.burn_in import get_video_info, burn_subtitles
from piccut.presets import load_presets, save_custom_preset, delete_custom_preset
from piccut.font_manager import get_font_em_ratio

logger = logging.getLogger(__name__)

def align_caption_tokens(
    new_tokens: List[str],
    old_words: List[Dict[str, Any]],
    cap_start: float,
    cap_end: float,
    prev_cap: Optional[Dict[str, Any]] = None,
    next_cap: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Intelligently align edited words with original Whisper timestamps.
    Preserves exact timing for untouched words, splits word timing proportionally when words
    are split, merges spans when tokens are joined, and inherits timestamps from adjacent cues
    if words were moved across cue boundaries.
    """
    if not new_tokens:
        return []

    if not old_words:
        span = max(0.2, cap_end - cap_start)
        step = span / len(new_tokens)
        return [
            {"word": tok, "start": round(cap_start + i * step, 3), "end": round(cap_start + (i + 1) * step, 3), "probability": 1.0}
            for i, tok in enumerate(new_tokens)
        ]

    if len(new_tokens) == len(old_words):
        res = []
        for i, tok in enumerate(new_tokens):
            w = dict(old_words[i])
            w["word"] = tok
            res.append(w)
        return res

    old_clean = [w["word"].lower().strip(".,!?\"'") for w in old_words]
    new_clean = [t.lower().strip(".,!?\"'") for t in new_tokens]
    matcher = difflib.SequenceMatcher(None, old_clean, new_clean)

    aligned: List[Optional[Dict[str, Any]]] = [None] * len(new_tokens)
    used_old = set()

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for old_idx, new_idx in zip(range(i1, i2), range(j1, j2)):
                aligned[new_idx] = dict(old_words[old_idx])
                aligned[new_idx]["word"] = new_tokens[new_idx]
                used_old.add(old_idx)
        elif tag == "replace" and (i2 - i1) == 1 and (j2 - j1) > 1:
            ow = old_words[i1]
            span = max(0.1, ow["end"] - ow["start"])
            sub_tokens = new_tokens[j1:j2]
            total_len = sum(max(1, len(t)) for t in sub_tokens)
            cur_t = ow["start"]
            for k, st in enumerate(sub_tokens):
                frac = max(1, len(st)) / total_len
                dur = round(span * frac, 3)
                w_end = round(cur_t + dur, 3) if k < len(sub_tokens) - 1 else ow["end"]
                aligned[j1 + k] = {"word": st, "start": cur_t, "end": w_end, "probability": 1.0}
                cur_t = w_end
            used_old.add(i1)
        elif tag == "replace" and (i2 - i1) > 1 and (j2 - j1) == 1:
            w_start = old_words[i1]["start"]
            w_end = old_words[i2 - 1]["end"]
            aligned[j1] = {"word": new_tokens[j1], "start": w_start, "end": w_end, "probability": 1.0}
            for idx in range(i1, i2):
                used_old.add(idx)

    # Check boundary words moved from adjacent cues
    if aligned[0] is None and prev_cap and prev_cap.get("words"):
        prev_words = prev_cap["words"]
        for p_idx in range(len(aligned)):
            if aligned[p_idx] is not None:
                break
            tok_clean = new_tokens[p_idx].lower().strip(".,!?\"'")
            match_found = False
            for pw in reversed(prev_words):
                if pw["word"].lower().strip(".,!?\"'") == tok_clean:
                    aligned[p_idx] = {"word": new_tokens[p_idx], "start": pw["start"], "end": pw["end"], "probability": 1.0}
                    match_found = True
                    break
            if not match_found:
                break

    if aligned[-1] is None and next_cap and next_cap.get("words"):
        next_words = next_cap["words"]
        for n_idx in range(len(aligned) - 1, -1, -1):
            if aligned[n_idx] is not None:
                break
            tok_clean = new_tokens[n_idx].lower().strip(".,!?\"'")
            match_found = False
            for nw in next_words:
                if nw["word"].lower().strip(".,!?\"'") == tok_clean:
                    aligned[n_idx] = {"word": new_tokens[n_idx], "start": nw["start"], "end": nw["end"], "probability": 1.0}
                    match_found = True
                    break
            if not match_found:
                break

    # Interpolate any remaining unassigned tokens between nearest known bounds
    for idx in range(len(aligned)):
        if aligned[idx] is None:
            prev_t = cap_start
            for p in range(idx - 1, -1, -1):
                if aligned[p] is not None:
                    prev_t = aligned[p]["end"]
                    break
            next_t = cap_end
            for n in range(idx + 1, len(aligned)):
                if aligned[n] is not None:
                    next_t = aligned[n]["start"]
                    break
            if next_t <= prev_t:
                next_t = round(prev_t + 0.3, 3)
            dur = round(max(0.08, (next_t - prev_t) / 2.0), 3)
            aligned[idx] = {"word": new_tokens[idx], "start": prev_t, "end": round(prev_t + dur, 3), "probability": 1.0}

    # Ensure strictly monotonic intervals
    for idx in range(1, len(aligned)):
        if aligned[idx]["start"] < aligned[idx - 1]["end"]:
            aligned[idx]["start"] = aligned[idx - 1]["end"]
        if aligned[idx]["end"] <= aligned[idx]["start"]:
            aligned[idx]["end"] = round(aligned[idx]["start"] + 0.08, 3)

    return aligned


def get_system_fonts() -> List[str]:
    """Retrieve installed system fonts on Windows + curated video typography fonts."""
    fonts = set([
        "Montserrat", "Impact", "Anton", "Bebas Neue", "Roboto", "Poppins",
        "Oswald", "Arial", "Trebuchet MS", "Futura", "Helvetica", "Verdana",
        "Segoe UI", "Comic Sans MS", "Franklin Gothic Medium", "Bahnschrift"
    ])
    if sys.platform == "win32":
        import winreg, re
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        ]
        for root_key, subkey in keys:
            try:
                k = winreg.OpenKey(root_key, subkey)
                for i in range(winreg.QueryInfoKey(k)[1]):
                    val_name, _, _ = winreg.EnumValue(k, i)
                    clean = re.sub(r"\s*\([^)]*\)$", "", val_name).strip()
                    family = re.sub(r"\s+(Regular|Bold|Italic|Light|SemiBold|Medium|Black|ExtraBold|Thin).*$", "", clean, flags=re.IGNORECASE).strip()
                    if family and len(family) > 1 and not family.startswith("@"):
                        fonts.add(family)
                winreg.CloseKey(k)
            except Exception:
                pass
    return sorted(list(fonts))

class AppApi:
    def __init__(self, window=None, server_port: int = 8765):
        self._window = window
        self.server_port = server_port
        
        self.current_video_path: Optional[str] = None
        self.video_info: Dict[str, Any] = {}
        self.raw_words: List[Dict[str, Any]] = []
        self.captions: List[Dict[str, Any]] = []
        
        self.target_words_per_caption: int = 3
        self.style_config = AssSubtitleConfig()
        self.crop_to_vertical: bool = True
        
        self.transcriber: Optional[Transcriber] = None
        self.is_busy: bool = False
        self._fonts: Optional[List[str]] = None

    def set_window(self, window):
        self._window = window

    def emit_event(self, event_name: str, data: Any = None):
        """Send an asynchronous event / callback into the WebView JavaScript."""
        if not self._window:
            return
        try:
            payload = json.dumps(data)
            js_code = f"window.onBackendEvent && window.onBackendEvent({json.dumps(event_name)}, {payload});"
            self._window.evaluate_js(js_code)
        except Exception as e:
            logger.debug(f"Failed to emit event {event_name}: {e}")

    def _sync_play_res(self):
        """Keep ASS PlayRes matching the active output resolution (1080x1920 if cropped vertical)."""
        if not self.video_info:
            return
        is_vertical = self.video_info.get("is_vertical", False)
        if self.crop_to_vertical and not is_vertical:
            self.style_config.play_res_x = 1080
            self.style_config.play_res_y = 1920
        else:
            self.style_config.play_res_x = self.video_info.get("width", 1080)
            self.style_config.play_res_y = self.video_info.get("height", 1920)

    def set_crop_to_vertical(self, crop: bool) -> Dict[str, Any]:
        """Toggle whether horizontal videos should be center-cropped to 9:16 vertical Shorts."""
        self.crop_to_vertical = bool(crop)
        self._sync_play_res()
        return {"success": True, "crop_to_vertical": self.crop_to_vertical}

    def get_init_data(self) -> Dict[str, Any]:
        """Fetch system capabilities, available fonts, and default configuration."""
        devices = get_available_devices()
        if self._fonts is None:
            self._fonts = get_system_fonts()
        return {
            "models": AVAILABLE_MODELS,
            "devices": devices,
            "default_model": "base",
            "default_device": devices["default_device"],
            "target_words": self.target_words_per_caption,
            "style": self.style_config.to_dict(),
            "fonts": self._fonts,
            "crop_to_vertical": self.crop_to_vertical,
            "presets": load_presets(),
            "font_em_ratio": get_font_em_ratio(self.style_config.font_family, self.style_config.font_weight),
        }

    def choose_video_file(self) -> Dict[str, Any]:
        """Open a native Windows file dialog to pick a video."""
        if not self._window:
            return {"error": "Window not initialized"}
        import webview
        dialog_type = getattr(webview.FileDialog, "OPEN", getattr(webview, "OPEN_DIALOG", 10))
        file_types = ("Video Files (*.mp4;*.mov;*.mkv;*.webm;*.avi)", "All Files (*.*)")
        result = self._window.create_file_dialog(
            dialog_type,
            allow_multiple=False,
            file_types=file_types
        )
        if not result or len(result) == 0:
            return {"cancelled": True}

        chosen_path = os.path.abspath(result[0])
        return self.load_video(chosen_path)

    def load_video(self, video_path: str) -> Dict[str, Any]:
        """Load a video file and return probe information."""
        if not os.path.isfile(video_path):
            return {"error": f"File does not exist: {video_path}"}

        self.current_video_path = video_path
        self.video_info = get_video_info(video_path)
        
        # Adjust ASS resolution to match video (or 1080x1920 if crop_to_vertical)
        self._sync_play_res()

        # Clear previous transcript
        self.raw_words = []
        self.captions = []

        stream_url = f"http://127.0.0.1:{self.server_port}/stream-video?path={video_path}"

        return {
            "success": True,
            "path": video_path,
            "filename": os.path.basename(video_path),
            "info": self.video_info,
            "preview_url": stream_url,
            "crop_to_vertical": self.crop_to_vertical
        }

    def start_transcription(
        self,
        model_size: str = "base",
        device: str = "cuda",
        language: str = "auto",
        target_words: int = 3
    ) -> Dict[str, Any]:
        """Start on-device transcription in a background thread."""
        if not self.current_video_path:
            return {"error": "No video selected"}
        if self.is_busy:
            return {"error": "Engine is currently busy"}

        self.target_words_per_caption = max(1, int(target_words))

        def _worker():
            self.is_busy = True
            try:
                self.emit_event("transcribe_progress", {"message": "Initializing model...", "percent": 5})

                transcriber = Transcriber(model_size=model_size, device=device)

                def on_progress(msg, pct):
                    self.emit_event("transcribe_progress", {"message": msg, "percent": pct})

                result = transcriber.transcribe(
                    self.current_video_path,
                    language=language,
                    progress_callback=on_progress
                )

                self.raw_words = result["words"]
                self.captions = chunk_words_to_captions(
                    self.raw_words,
                    target_words_per_caption=self.target_words_per_caption
                )

                self.emit_event("transcribe_complete", {
                    "language": result["language"],
                    "duration": result["duration"],
                    "captions": self.captions,
                    "word_count": len(self.raw_words),
                })
            except Exception as e:
                logger.exception("Transcription failed")
                self.emit_event("transcribe_error", {"error": str(e)})
            finally:
                self.is_busy = False

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return {"started": True}

    def rechunk(self, target_words: int) -> Dict[str, Any]:
        """Re-chunk existing transcribed words into a new target word count."""
        if not self.raw_words:
            return {"error": "No transcription available"}

        self.target_words_per_caption = max(1, int(target_words))
        self.captions = chunk_words_to_captions(
            self.raw_words,
            target_words_per_caption=self.target_words_per_caption
        )
        return {"captions": self.captions}

    def _sync_caption_durations(self):
        """Extend previous valid cue's duration across any subsequent empty cue(s)."""
        prev_valid = None
        for cap in self.captions:
            if "orig_start" not in cap:
                cap["orig_start"] = cap["start"]
            if "orig_end" not in cap:
                cap["orig_end"] = cap["end"]

            clean_text = cap.get("text", "").strip()
            words = [w for w in cap.get("words", []) if w.get("word", "").strip()]
            if not clean_text or not words:
                # Empty cue: extend previous valid cue
                if prev_valid is not None:
                    cap_end = cap.get("orig_end", cap.get("end", prev_valid["end"]))
                    prev_valid["end"] = max(prev_valid["end"], cap_end)
            else:
                # Reset to own bounds
                if cap.get("words"):
                    cap["start"] = cap["words"][0]["start"]
                    cap["end"] = cap["words"][-1]["end"]
                else:
                    cap["start"] = cap.get("orig_start", cap["start"])
                    cap["end"] = cap.get("orig_end", cap["end"])
                prev_valid = cap

    def update_caption(self, caption_id: int, new_text: str) -> Dict[str, Any]:
        """Update the text of a specific caption line with smart word alignment and duration extension."""
        if 0 <= caption_id < len(self.captions):
            cap = self.captions[caption_id]
            clean_text = new_text.strip()
            cap["text"] = clean_text
            
            if "orig_start" not in cap:
                cap["orig_start"] = cap["start"]
            if "orig_end" not in cap:
                cap["orig_end"] = cap["end"]

            new_word_tokens = clean_text.split()
            old_words = cap.get("words", [])
            prev_cap = self.captions[caption_id - 1] if caption_id > 0 else None
            next_cap = self.captions[caption_id + 1] if caption_id < len(self.captions) - 1 else None

            if not new_word_tokens:
                cap["words"] = []
            else:
                cap["words"] = align_caption_tokens(
                    new_word_tokens,
                    old_words,
                    cap.get("orig_start", cap["start"]),
                    cap.get("orig_end", cap["end"]),
                    prev_cap=prev_cap,
                    next_cap=next_cap
                )
                if cap["words"]:
                    cap["start"] = cap["words"][0]["start"]
                    cap["end"] = cap["words"][-1]["end"]

            self._sync_caption_durations()
            return {"success": True, "caption": cap, "captions": self.captions}
        return {"error": "Invalid caption ID"}

    def update_style(self, style_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Update subtitle styling configuration and return updated font em ratio."""
        try:
            self.style_config = AssSubtitleConfig.from_dict(style_dict)
            self._sync_play_res()
            em_ratio = get_font_em_ratio(self.style_config.font_family, self.style_config.font_weight)
            return {
                "success": True,
                "style": self.style_config.to_dict(),
                "font_em_ratio": em_ratio
            }
        except Exception as e:
            return {"error": str(e)}

    def get_font_metrics(self, font_family: str, weight: int = 800) -> Dict[str, Any]:
        """Return font metrics including em_ratio for preview scaling."""
        ratio = get_font_em_ratio(font_family, weight)
        return {"font_family": font_family, "weight": weight, "em_ratio": ratio}

    def get_presets(self) -> Dict[str, Any]:
        """Fetch all available style presets."""
        return {"presets": load_presets()}

    def save_preset(self, name: str, style_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Save a new custom style preset or update an existing one."""
        try:
            presets = save_custom_preset(name, style_dict)
            return {"success": True, "presets": presets}
        except Exception as e:
            return {"error": str(e)}

    def delete_preset(self, name: str) -> Dict[str, Any]:
        """Delete a custom style preset."""
        try:
            presets = delete_custom_preset(name)
            return {"success": True, "presets": presets}
        except Exception as e:
            return {"error": str(e)}

    def burn_in_and_export(self, custom_output_name: Optional[str] = None) -> Dict[str, Any]:
        """Generate ASS subtitles and burn them in using FFmpeg."""
        if not self.current_video_path:
            return {"error": "No video loaded"}
        if not self.captions:
            return {"error": "No subtitles to burn in"}
        if self.is_busy:
            return {"error": "Process already running"}

        base_dir = os.path.dirname(self.current_video_path)
        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        
        out_filename = custom_output_name or f"{base_name}_subtitled.mp4"
        output_path = os.path.join(base_dir, out_filename)
        ass_path = os.path.join(base_dir, f"{base_name}_temp_subtitles.ass")

        def _worker():
            self.is_busy = True
            try:
                self.emit_event("burn_progress", {"message": "Generating subtitle script...", "percent": 5})

                # Ensure resolution matches export target
                self._sync_play_res()

                # Write ASS file
                ass_content = generate_ass_content(self.captions, self.style_config)
                with open(ass_path, "w", encoding="utf-8") as f:
                    f.write(ass_content)

                def on_progress(msg, pct):
                    self.emit_event("burn_progress", {"message": msg, "percent": pct})

                final_path = burn_subtitles(
                    self.current_video_path,
                    ass_path,
                    output_path,
                    use_gpu=True,
                    progress_callback=on_progress,
                    crop_to_vertical=self.crop_to_vertical
                )

                # Clean up temp ASS file
                try:
                    if os.path.exists(ass_path):
                        os.remove(ass_path)
                except Exception:
                    pass

                self.emit_event("burn_complete", {
                    "output_path": final_path,
                    "filename": os.path.basename(final_path)
                })
            except Exception as e:
                logger.exception("Burn-in failed")
                self.emit_event("burn_error", {"error": str(e)})
            finally:
                self.is_busy = False

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return {"started": True, "output_path": output_path}

    def export_subtitles_file(self, format_type: str = "srt", custom_filename: Optional[str] = None) -> Dict[str, Any]:
        """Export subtitles directly to a standalone .srt or .ass file in the video's directory."""
        if not self.current_video_path:
            return {"error": "No video loaded"}
        if not self.captions:
            return {"error": "No subtitles to export"}

        fmt = format_type.lower().strip()
        if fmt not in ("srt", "ass"):
            return {"error": f"Unsupported format: {format_type}. Must be 'srt' or 'ass'."}

        base_dir = os.path.dirname(self.current_video_path)
        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        default_name = custom_filename or f"{base_name}.{fmt}"
        output_path = os.path.join(base_dir, default_name)

        try:
            if fmt == "srt":
                content = generate_srt_content(self.captions)
            else:
                self._sync_play_res()
                content = generate_ass_content(self.captions, self.style_config)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "format": fmt,
                "output_path": os.path.abspath(output_path),
                "filename": os.path.basename(output_path)
            }
        except Exception as e:
            logger.exception(f"Failed to export {fmt.upper()} subtitles")
            return {"error": str(e)}

    def choose_and_export_subtitles(self, format_type: str = "srt") -> Dict[str, Any]:
        """Open a native file dialog to export .srt or .ass subtitles to user-specified location."""
        if not self.current_video_path:
            return {"error": "No video loaded"}
        if not self.captions:
            return {"error": "No subtitles to export"}

        fmt = format_type.lower().strip()
        if fmt not in ("srt", "ass"):
            return {"error": f"Unsupported format: {format_type}. Must be 'srt' or 'ass'."}

        if not self._window:
            return {"error": "Window not initialized"}
        import webview
        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        default_name = f"{base_name}.{fmt}"

        dialog_type = getattr(webview.FileDialog, "SAVE", getattr(webview, "SAVE_DIALOG", 30))
        file_types = (f"{fmt.upper()} Subtitle Files (*.{fmt})", "All Files (*.*)")
        result = self._window.create_file_dialog(
            dialog_type,
            save_filename=default_name,
            file_types=file_types
        )
        if not result:
            return {"cancelled": True}

        chosen_path = result if isinstance(result, str) else result[0]
        if not chosen_path:
            return {"cancelled": True}
        if not chosen_path.lower().endswith(f".{fmt}"):
            chosen_path = f"{chosen_path}.{fmt}"

        try:
            if fmt == "srt":
                content = generate_srt_content(self.captions)
            else:
                self._sync_play_res()
                content = generate_ass_content(self.captions, self.style_config)

            with open(chosen_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "format": fmt,
                "output_path": os.path.abspath(chosen_path),
                "filename": os.path.basename(chosen_path)
            }
        except Exception as e:
            logger.exception(f"Failed to export {fmt.upper()}")
            return {"error": str(e)}

    def open_output_folder(self, file_path: str):
        """Open the output folder in Windows File Explorer."""
        if not os.path.exists(file_path):
            file_path = os.path.dirname(file_path)
        if os.name == "nt":
            import subprocess
            subprocess.run(["explorer", "/select,", os.path.abspath(file_path)])
        return {"success": True}
