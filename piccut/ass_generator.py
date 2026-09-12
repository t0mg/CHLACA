"""Advanced SubStation Alpha (.ass) generator for animated word-highlight subtitles.
Generates pixel-perfect per-word highlighted subtitles for vertical 9:16 videos.
"""

import sys
from typing import List, Dict, Any, Optional
from piccut.font_manager import resolve_font_for_ass

def hex_to_ass_color(hex_str: str, alpha: int = 0) -> str:
    """Convert a hex color string (#RRGGBB or RRGGBB) to ASS color format &HAABBGGRR&.
    In ASS:
      AA: Alpha (00 = fully opaque, FF = fully transparent)
      BB: Blue channel
      GG: Green channel
      RR: Red channel
    """
    clean_hex = hex_str.strip().lstrip("#")
    if len(clean_hex) == 3:
        clean_hex = "".join([c * 2 for c in clean_hex])
    if len(clean_hex) < 6:
        clean_hex = clean_hex.ljust(6, "0")
        
    r = clean_hex[0:2].upper()
    g = clean_hex[2:4].upper()
    b = clean_hex[4:6].upper()
    a = f"{max(0, min(255, alpha)):02X}"
    
    return f"&H{a}{b}{g}{r}&"

def format_ass_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format: H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = rem % 60
    secs_int = int(secs)
    centis = int(round((secs - secs_int) * 100))
    if centis >= 100:
        secs_int += 1
        centis -= 100
        if secs_int >= 60:
            mins += 1
            secs_int -= 60
            if mins >= 60:
                hrs += 1
                mins -= 60
    return f"{hrs}:{mins:02d}:{secs_int:02d}.{centis:02d}"

def measure_text_width(text: str, font_name: str, font_size: int, font_weight: int = 800) -> int:
    """Measure the pixel width of rendered text using Windows GDI, with a heuristic fallback."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(0)
            hfont = gdi32.CreateFontW(
                font_size, 0, 0, 0,
                font_weight,
                0, 0, 0, 1, 0, 0, 0, 0,
                font_name
            )
            old_font = gdi32.SelectObject(hdc, hfont)
            class SIZE(ctypes.Structure):
                _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]
            sz = SIZE()
            gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(sz))
            gdi32.SelectObject(hdc, old_font)
            gdi32.DeleteObject(hfont)
            user32.ReleaseDC(0, hdc)
            if sz.cx > 0:
                return int(sz.cx)
        except Exception:
            pass
    return int(len(text) * font_size * 0.55)

def make_rounded_rect_path(width: int, height: int, radius: int) -> str:
    """Generate ASS drawing vector path for a rounded rectangle with smooth bezier corners."""
    r = max(4, min(radius, width // 2, height // 2))
    k = int(round(r * 0.55228475))
    return (
        f"m {r} 0 "
        f"l {width - r} 0 "
        f"b {width - r + k} 0 {width} {r - k} {width} {r} "
        f"l {width} {height - r} "
        f"b {width} {height - r + k} {width - r + k} {height} {width - r} {height} "
        f"l {r} {height} "
        f"b {r - k} {height} 0 {height - r + k} 0 {height - r} "
        f"l 0 {r} "
        f"b 0 {r - k} {r - k} 0 {r} 0"
    )

class AssSubtitleConfig:
    def __init__(
        self,
        font_family: str = "Montserrat",
        font_size: int = 68,
        font_weight: int = 800,
        front_color: str = "#FFFFFF",
        back_color: str = "#000000",
        enable_background_box: bool = False,
        background_color: str = "#000000",
        background_alpha: int = 89,
        enable_highlight: bool = True,
        highlight_font: Optional[str] = None,
        highlight_size: Optional[int] = None,
        highlight_size_delta: Optional[int] = None,
        highlight_front_color: str = "#FFE600",
        highlight_back_color: str = "#000000",
        vertical_position_pct: float = 72.0,
        outline_width: float = 0.0,
        shadow_depth: float = 2.0,
        play_res_x: int = 1080,
        play_res_y: int = 1920,
        enable_pop_effect: bool = True
    ):
        self.font_family = font_family
        self.font_size = font_size
        self.font_weight = font_weight
        self.front_color = front_color
        self.back_color = back_color
        
        self.enable_background_box = enable_background_box
        self.background_color = background_color
        self.background_alpha = background_alpha
        
        self.enable_highlight = enable_highlight
        self.highlight_font = highlight_font or font_family
        
        # Highlight size can be defined as an absolute size or delta from base font_size
        if highlight_size_delta is not None:
            self.highlight_size_delta = int(highlight_size_delta)
            self.highlight_size = max(12, self.font_size + self.highlight_size_delta)
        elif highlight_size is not None:
            self.highlight_size = int(highlight_size)
            self.highlight_size_delta = self.highlight_size - self.font_size
        else:
            self.highlight_size = self.font_size
            self.highlight_size_delta = 0

        self.highlight_front_color = highlight_front_color
        self.highlight_back_color = highlight_back_color
        
        # Vertical position: 0% = top, 50% = middle, 72% = shorts safe zone, 100% = bottom
        self.vertical_position_pct = max(0.0, min(100.0, vertical_position_pct))
        self.outline_width = outline_width
        self.shadow_depth = shadow_depth
        self.play_res_x = play_res_x
        self.play_res_y = play_res_y
        self.enable_pop_effect = enable_pop_effect

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "front_color": self.front_color,
            "back_color": self.back_color,
            "enable_background_box": self.enable_background_box,
            "background_color": self.background_color,
            "background_alpha": self.background_alpha,
            "enable_highlight": self.enable_highlight,
            "highlight_font": self.highlight_font,
            "highlight_size": self.highlight_size,
            "highlight_size_delta": self.highlight_size_delta,
            "highlight_front_color": self.highlight_front_color,
            "highlight_back_color": self.highlight_back_color,
            "vertical_position_pct": self.vertical_position_pct,
            "outline_width": self.outline_width,
            "shadow_depth": self.shadow_depth,
            "play_res_x": self.play_res_x,
            "play_res_y": self.play_res_y,
            "enable_pop_effect": self.enable_pop_effect,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AssSubtitleConfig":
        hl_delta = data.get("highlight_size_delta")
        hl_size = data.get("highlight_size")
        return cls(
            font_family=data.get("font_family", "Montserrat"),
            font_size=int(data.get("font_size", 68)),
            font_weight=int(data.get("font_weight", 800)),
            front_color=data.get("front_color", "#FFFFFF"),
            back_color=data.get("back_color", "#000000"),
            enable_background_box=bool(data.get("enable_background_box", False)),
            background_color=data.get("background_color", "#000000"),
            background_alpha=int(data.get("background_alpha", 89)),
            enable_highlight=bool(data.get("enable_highlight", True)),
            highlight_font=data.get("highlight_font") or data.get("font_family", "Montserrat"),
            highlight_size=int(hl_size) if hl_size is not None else None,
            highlight_size_delta=int(hl_delta) if hl_delta is not None else None,
            highlight_front_color=data.get("highlight_front_color", "#FFE600"),
            highlight_back_color=data.get("highlight_back_color", "#000000"),
            vertical_position_pct=float(data.get("vertical_position_pct", 72.0)),
            outline_width=float(data.get("outline_width", 0.0)),
            shadow_depth=float(data.get("shadow_depth", 2.0)),
            play_res_x=int(data.get("play_res_x", 1080)),
            play_res_y=int(data.get("play_res_y", 1920)),
            enable_pop_effect=bool(data.get("enable_pop_effect", True))
        )

def generate_ass_content(
    captions: List[Dict[str, Any]],
    config: AssSubtitleConfig
) -> str:
    """Generate the full text content of an .ass subtitle file."""
    # Convert colors
    primary_color_ass = hex_to_ass_color(config.front_color)
    outline_color_ass = hex_to_ass_color(config.back_color)
    shadow_color_ass = hex_to_ass_color(config.back_color, alpha=140)
    
    hl_primary_ass = hex_to_ass_color(config.highlight_front_color)
    hl_outline_ass = hex_to_ass_color(config.highlight_back_color)
    
    # MarginV: distance from bottom for Alignment 2 fallback
    margin_v = int(round((1.0 - (config.vertical_position_pct / 100.0)) * config.play_res_y))
    margin_v = max(20, min(config.play_res_y - 80, margin_v))

    # Outline & Shadow
    if config.outline_width > 0:
        outline_val = config.outline_width
        shadow_val = config.shadow_depth
    else:
        outline_val = 0.0
        shadow_val = 0.0

    # Resolve true font names for ASS and libass
    base_font_name, _, base_ass_weight = resolve_font_for_ass(config.font_family, config.font_weight)
    hl_family = config.highlight_font or config.font_family
    hl_font_name, _, hl_ass_weight = resolve_font_for_ass(hl_family, config.font_weight)
    ass_bold_val = base_ass_weight if base_ass_weight > 0 else (1 if config.font_weight >= 600 else 0)

    styles = []
    if config.enable_background_box:
        bg_color_ass = hex_to_ass_color(config.background_color, alpha=config.background_alpha)
        # BgShape style: Alignment 7 (top-left) with 0 margins, used for vector drawings on Layer 0
        styles.append(
            f"Style: BgShape,{base_font_name},{config.font_size},{bg_color_ass},&H00000000&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
        )
    
    styles.append(
        f"Style: Default,{base_font_name},{config.font_size},{primary_color_ass},&H000000FF&,{outline_color_ass},{shadow_color_ass},{ass_bold_val},0,0,0,100,100,0,0,1,{outline_val},{shadow_val},2,40,40,{margin_v},1"
    )
    styles_str = "\n".join(styles)

    header = f"""[Script Info]
Title: PicCut YouTube Shorts Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {config.play_res_x}
PlayResY: {config.play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles_str}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    target_x = config.play_res_x // 2
    target_y = int(round(config.play_res_y * (config.vertical_position_pct / 100.0)))
    target_y = max(40, min(config.play_res_y - 40, target_y))

    # Filter empty cues and extend previous non-empty cue's end duration to fill in
    active_captions = []
    prev_valid_cap = None
    for cap in captions:
        cap_words = [w for w in cap.get("words", []) if w.get("word", "").strip()]
        cap_text = cap.get("text", "").strip()
        if not cap_words or not cap_text:
            # Empty cue: extend previous cue's end time to fill in this cue's duration
            if prev_valid_cap is not None:
                cap_end = cap.get("end", prev_valid_cap["end"])
                if cap_end > prev_valid_cap["end"]:
                    prev_valid_cap["end"] = cap_end
            continue
        c_copy = dict(cap)
        c_copy["words"] = cap_words
        c_copy["text"] = cap_text
        active_captions.append(c_copy)
        prev_valid_cap = c_copy

    for cap in active_captions:
        words = cap.get("words", [])
        if not words:
            continue

        c_start = cap.get("start", words[0]["start"])
        c_end = cap.get("end", words[-1]["end"])
        if c_end <= c_start:
            c_end = c_start + 0.5

        start_str_full = format_ass_time(c_start)
        end_str_full = format_ass_time(c_end)
        full_text = cap.get("text", " ".join(w["word"] for w in words)).strip()

        # Measure text and calculate line wrapping if text exceeds safe width
        max_content_w = config.play_res_x - 80
        tw = measure_text_width(full_text, base_font_name, config.font_size, config.font_weight)
        pad_x = int(round(config.font_size * 0.38))

        line_indices = []
        curr_line = []
        for idx, w in enumerate(words):
            cand_words = [words[k]["word"] for k in curr_line + [idx]]
            cand_text = " ".join(cand_words)
            if curr_line and measure_text_width(cand_text, base_font_name, config.font_size, config.font_weight) > max_content_w:
                line_indices.append(curr_line)
                curr_line = [idx]
            else:
                curr_line.append(idx)
        if curr_line:
            line_indices.append(curr_line)

        num_lines = len(line_indices)

        # Background box calculation
        if config.enable_background_box:
            if num_lines > 1:
                max_lw = max(
                    measure_text_width(" ".join(words[k]["word"] for k in l_idx), base_font_name, config.font_size, config.font_weight)
                    for l_idx in line_indices
                )
                box_w = min(config.play_res_x - 40, max_lw + pad_x * 2)
                line_h = int(round(config.font_size * 0.78))
                box_h = int(round(line_h * num_lines + config.font_size * 0.18))
                box_center_y = target_y - int(round(config.font_size * 0.06))
            else:
                box_w = min(config.play_res_x - 40, tw + pad_x * 2)
                box_h = int(round(config.font_size * 0.88))
                box_center_y = target_y - int(round(config.font_size * 0.08))

            box_x = (config.play_res_x - box_w) // 2
            box_y = box_center_y - (box_h // 2)
            r = min(12, max(4, box_h // 5), box_w // 2)
            path = make_rounded_rect_path(box_w, box_h, r)

            events.append(f"Dialogue: 0,{start_str_full},{end_str_full},BgShape,,0,0,0,,{{\\an7\\pos({box_x},{box_y})\\bord0\\shad0\\p1}}{path}{{\\p0}}")

        text_layer = 1 if config.enable_background_box else 0

        def build_line_text(active_idx: Optional[int]) -> str:
            formatted_lines = []
            for l_idx in line_indices:
                line_words = []
                for j in l_idx:
                    w_text = words[j]["word"]
                    if active_idx is not None and j == active_idx:
                        tags = [f"\\c{hl_primary_ass}"]
                        if config.outline_width > 0:
                            tags.append(f"\\3c{hl_outline_ass}")
                        if hl_font_name != base_font_name:
                            tags.append(f"\\fn{hl_font_name}")
                        if config.highlight_size != config.font_size:
                            tags.append(f"\\fs{config.highlight_size}")
                        if hl_ass_weight > 0:
                            tags.append(f"\\b{hl_ass_weight}")
                        if config.enable_pop_effect:
                            tags.append(r"\t(0,60,\fscx108\fscy108)")
                        line_words.append(f"{{{''.join(tags)}}}{w_text}{{\\r\\fn{base_font_name}\\b{ass_bold_val}}}")
                    else:
                        line_words.append(w_text)
                formatted_lines.append(" ".join(line_words))
            return r"\N".join(formatted_lines)

        if not config.enable_highlight:
            dialogue_text = build_line_text(None)
            events.append(f"Dialogue: {text_layer},{start_str_full},{end_str_full},Default,,0,0,0,,{{\\an5\\pos({target_x},{target_y})}}{dialogue_text}")
            continue

        # Active word highlighting per interval
        # Each word interval spans contiguously to the next word's start, or to cue_end for the last word,
        # ensuring the dialogue text is continuously rendered on Layer 1 without gaps or flickering.
        cue_start = float(cap.get("start", words[0]["start"]))
        cue_end = float(cap.get("end", words[-1]["end"]))

        for i, target_word in enumerate(words):
            int_start = cue_start if i == 0 else target_word["start"]
            int_end = words[i + 1]["start"] if (i < len(words) - 1) else max(target_word["end"], cue_end)

            if int_end <= int_start:
                int_end = int_start + 0.08

            start_str = format_ass_time(int_start)
            end_str = format_ass_time(int_end)

            dialogue_text = build_line_text(i)
            events.append(f"Dialogue: {text_layer},{start_str},{end_str},Default,,0,0,0,,{{\\an5\\pos({target_x},{target_y})}}{dialogue_text}")

    return header + "\n".join(events) + "\n"


def format_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm (milliseconds)."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    rem = seconds % 3600
    mins = int(rem // 60)
    secs = rem % 60
    secs_int = int(secs)
    millis = int(round((secs - secs_int) * 1000))
    if millis >= 1000:
        secs_int += 1
        millis -= 1000
        if secs_int >= 60:
            mins += 1
            secs_int -= 60
            if mins >= 60:
                hrs += 1
                mins -= 60
    return f"{hrs:02d}:{mins:02d}:{secs_int:02d},{millis:03d}"


def generate_srt_content(captions: List[Dict[str, Any]]) -> str:
    """Generate the full text content of a standard .srt subtitle file."""
    active_captions = []
    prev_valid = None
    for cap in captions:
        text = cap.get("text", "").strip()
        if not text:
            if prev_valid is not None:
                cap_end = cap.get("end", prev_valid.get("end", 0.0))
                if cap_end > prev_valid.get("end", 0.0):
                    prev_valid["end"] = cap_end
            continue
        c_copy = dict(cap)
        active_captions.append(c_copy)
        prev_valid = c_copy

    blocks = []
    for idx, cap in enumerate(active_captions, start=1):
        text = cap.get("text", "").strip()
        start_str = format_srt_time(cap.get("start", 0.0))
        end_str = format_srt_time(cap.get("end", 0.0))
        blocks.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    return "\n".join(blocks)

