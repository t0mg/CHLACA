"""Font manager for resolving and providing static fonts to libass and Windows GDI.
Handles downloading static TTF weights from Google Fonts for variable fonts (e.g. Syne, Montserrat),
registering fonts with Windows GDI (for exact text metric measurement), and providing the font directory
to FFmpeg's libass filter.
"""

import os
import sys
import re
import struct
import urllib.request
import urllib.parse
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

WEIGHT_SUBFAMILIES = {
    100: "Thin",
    200: "ExtraLight",
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black"
}

_GDI_REGISTERED_FONTS = set()
_RESOLVED_FONT_CACHE: Dict[Tuple[str, int], Tuple[str, str, int]] = {}

def get_fonts_cache_dir() -> str:
    """Return the absolute path to the local PicCut fonts cache directory."""
    cache_dir = os.path.join(os.path.expanduser("~"), ".piccut", "fonts")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir

def parse_ttf_names(path: str) -> Dict[int, str]:
    """Parse Name table records from a TrueType / OpenType font file.
    Returns mapping of nameID -> string value.
    Key Name IDs:
      1: Font Family Name (e.g. 'Syne ExtraBold')
      2: Font Subfamily Name (e.g. 'Regular')
      4: Full Font Name (e.g. 'Syne ExtraBold')
      16: Typographic Family Name (e.g. 'Syne')
      17: Typographic Subfamily Name (e.g. 'ExtraBold')
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 12:
            return {}
        num_tables = struct.unpack(">H", data[4:6])[0]
        name_offset = None
        for i in range(num_tables):
            entry_offset = 12 + i * 16
            tag = data[entry_offset:entry_offset + 4].decode("latin1", "ignore")
            if tag == "name":
                name_offset = struct.unpack(">I", data[entry_offset + 8:entry_offset + 12])[0]
                break
        if not name_offset or name_offset + 6 > len(data):
            return {}
        fmt, count, string_offset = struct.unpack(">HHH", data[name_offset:name_offset + 6])
        string_base = name_offset + string_offset
        names = {}
        for i in range(count):
            rec_offset = name_offset + 6 + i * 12
            if rec_offset + 12 > len(data):
                break
            platform_id, encoding_id, language_id, name_id, length, offset = struct.unpack(
                ">HHHHHH", data[rec_offset:rec_offset + 12]
            )
            raw = data[string_base + offset:string_base + offset + length]
            if platform_id in (0, 3):  # Unicode (UTF-16BE)
                try:
                    val = raw.decode("utf-16be")
                except Exception:
                    val = str(raw)
            else:
                try:
                    val = raw.decode("utf-8")
                except Exception:
                    val = raw.decode("latin1", "ignore")
            names[name_id] = val
        return names
    except Exception as e:
        logger.debug(f"Failed to parse TTF names from {path}: {e}")
        return {}

def register_font_for_gdi(font_path: str):
    """Register font file privately with Windows GDI so GetTextExtentPoint32W can measure it."""
    if sys.platform != "win32":
        return
    norm_path = os.path.abspath(font_path)
    if norm_path in _GDI_REGISTERED_FONTS:
        return
    try:
        import ctypes
        gdi32 = ctypes.windll.gdi32
        # FR_PRIVATE = 0x10
        res = gdi32.AddFontResourceExW(norm_path, 0x10, 0)
        if res > 0:
            _GDI_REGISTERED_FONTS.add(norm_path)
            logger.info(f"Registered font in GDI: {norm_path}")
    except Exception as e:
        logger.debug(f"Could not register font with GDI ({norm_path}): {e}")

def get_installed_windows_font_names() -> Dict[str, str]:
    """Return dictionary of font title -> font filename from Windows Registry."""
    if sys.platform != "win32":
        return {}
    fonts = {}
    import winreg
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
    ]
    for root_key, subkey in keys:
        try:
            k = winreg.OpenKey(root_key, subkey)
            for i in range(winreg.QueryInfoKey(k)[1]):
                val_name, val_data, _ = winreg.EnumValue(k, i)
                clean = re.sub(r"\s*\([^)]*\)$", "", val_name).strip()
                fonts[clean.lower()] = clean
            winreg.CloseKey(k)
        except Exception:
            pass
    return fonts

def download_google_font_static(family: str, weight: int) -> Optional[str]:
    """Attempt to download a static TTF font for the given family and weight from Google Fonts.
    Saves to the local ~/.piccut/fonts cache directory.
    """
    cache_dir = get_fonts_cache_dir()
    safe_name = re.sub(r"[^\w\-]", "", family)
    target_path = os.path.join(cache_dir, f"{safe_name}_{weight}.ttf")
    if os.path.isfile(target_path) and os.path.getsize(target_path) > 1000:
        return target_path

    try:
        encoded_family = urllib.parse.quote(family)
        css_url = f"https://fonts.googleapis.com/css2?family={encoded_family}:wght@{weight}"
        req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            css_text = resp.read().decode("utf-8", "ignore")

        # Extract .ttf url
        match = re.search(r"src:\s*url\((https://[^)]+\.ttf)\)", css_text)
        if not match:
            return None

        ttf_url = match.group(1)
        font_req = urllib.request.Request(ttf_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(font_req, timeout=10) as f_resp:
            font_bytes = f_resp.read()

        if len(font_bytes) > 1000:
            with open(target_path, "wb") as f_out:
                f_out.write(font_bytes)
            logger.info(f"Downloaded static font {family} (weight {weight}) to {target_path}")
            return target_path
    except Exception as e:
        logger.debug(f"Could not download static font for {family} @ {weight}: {e}")
    return None

def resolve_font_for_ass(family: str, weight: int = 800) -> Tuple[str, str, int]:
    """Resolve font family and weight to the best matching font name for ASS and libass.
    
    Returns:
        (ass_font_name, fonts_dir, ass_weight)
        
    If a static font file with true weight (e.g. Syne ExtraBold) is downloaded or found in cache:
      ass_font_name = 'Syne ExtraBold'
      fonts_dir = '~/.piccut/fonts'
      ass_weight = 0 (since the font file is already intrinsically ExtraBold)
    """
    cache_key = (family.strip().lower(), weight)
    if cache_key in _RESOLVED_FONT_CACHE:
        return _RESOLVED_FONT_CACHE[cache_key]

    fonts_dir = get_fonts_cache_dir()
    clean_family = family.strip()
    subfamily = WEIGHT_SUBFAMILIES.get(weight, "")

    # Check existing files in fonts_dir first
    safe_name = re.sub(r"[^\w\-]", "", clean_family)
    existing_candidates = [
        os.path.join(fonts_dir, f"{safe_name}_{weight}.ttf"),
        os.path.join(fonts_dir, f"{safe_name}-{subfamily}.ttf") if subfamily else None
    ]
    for c in existing_candidates:
        if c and os.path.isfile(c) and os.path.getsize(c) > 1000:
            names = parse_ttf_names(c)
            register_font_for_gdi(c)
            ass_weight = 1 if weight >= 600 else 0
            font_name = names.get(1) or names.get(4) or f"{clean_family} {subfamily}".strip()
            res = (font_name, fonts_dir, ass_weight)
            _RESOLVED_FONT_CACHE[cache_key] = res
            return res

    # Check if Windows registry has a distinct static font for this weight (e.g. "Segoe UI Black")
    if sys.platform == "win32" and subfamily:
        installed = get_installed_windows_font_names()
        cand = f"{clean_family} {subfamily}".lower()
        if cand in installed:
            ass_weight = 1 if weight >= 600 else 0
            res = (installed[cand], fonts_dir, ass_weight)
            _RESOLVED_FONT_CACHE[cache_key] = res
            return res

    # If weight is standard 400 or bold 700 on a known system font without variable font issues
    # try downloading static font from Google Fonts if weight >= 600 (where variable fonts fail in libass)
    if weight >= 600:
        downloaded = download_google_font_static(clean_family, weight)
        if downloaded and os.path.isfile(downloaded):
            names = parse_ttf_names(downloaded)
            register_font_for_gdi(downloaded)
            font_name = names.get(1) or names.get(4) or f"{clean_family} {subfamily}".strip()
            ass_weight = 1 if weight >= 600 else 0
            res = (font_name, fonts_dir, ass_weight)
            _RESOLVED_FONT_CACHE[cache_key] = res
            return res

    # Fallback to family name with numeric weight
    res = (clean_family, fonts_dir, weight)
    _RESOLVED_FONT_CACHE[cache_key] = res
    return res


_FONT_EM_RATIO_CACHE: Dict[Tuple[str, int], float] = {}

def get_font_em_ratio(family: str, weight: int = 800) -> float:
    """Calculate the Em-to-Cell height ratio (em_height / cell_height) for a font.
    
    Windows DirectWrite and GDI (which libass uses) treat Fontsize as cell height (tmHeight).
    CSS in web browsers treats font-size as em height.
    This ratio (typically 0.55 to 0.90) allows web previews to scale font-size so that
    rendered text in the preview matches the exact visual proportions produced by libass.
    """
    clean_family = family.strip()
    cache_key = (clean_family.lower(), weight)
    if cache_key in _FONT_EM_RATIO_CACHE:
        return _FONT_EM_RATIO_CACHE[cache_key]

    if sys.platform != "win32":
        return 0.72

    try:
        import ctypes
        from ctypes import wintypes

        class TEXTMETRICW(ctypes.Structure):
            _fields_ = [
                ('tmHeight', wintypes.LONG),
                ('tmAscent', wintypes.LONG),
                ('tmDescent', wintypes.LONG),
                ('tmInternalLeading', wintypes.LONG),
                ('tmExternalLeading', wintypes.LONG),
                ('tmAveCharWidth', wintypes.LONG),
                ('tmMaxCharWidth', wintypes.LONG),
                ('tmWeight', wintypes.LONG),
                ('tmOverhang', wintypes.LONG),
                ('tmDigitizedAspectX', wintypes.LONG),
                ('tmDigitizedAspectY', wintypes.LONG),
                ('tmFirstChar', wintypes.WCHAR),
                ('tmLastChar', wintypes.WCHAR),
                ('tmDefaultChar', wintypes.WCHAR),
                ('tmBreakChar', wintypes.WCHAR),
                ('tmItalic', wintypes.BYTE),
                ('tmUnderlined', wintypes.BYTE),
                ('tmStruckOut', wintypes.BYTE),
                ('tmPitchAndFamily', wintypes.BYTE),
                ('tmCharSet', wintypes.BYTE),
            ]

        resolved_name, _, _ = resolve_font_for_ass(clean_family, weight)
        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        hdc = user32.GetDC(0)
        hfont = gdi32.CreateFontW(1000, 0, 0, 0, weight, 0, 0, 0, 1, 0, 0, 0, 0, resolved_name)
        old_obj = gdi32.SelectObject(hdc, hfont)
        tm = TEXTMETRICW()
        gdi32.GetTextMetricsW(hdc, ctypes.byref(tm))
        gdi32.SelectObject(hdc, old_obj)
        gdi32.DeleteObject(hfont)
        user32.ReleaseDC(0, hdc)

        if tm.tmHeight > 0:
            em_h = tm.tmHeight - tm.tmInternalLeading
            ratio = round(em_h / tm.tmHeight, 4)
            _FONT_EM_RATIO_CACHE[cache_key] = ratio
            return ratio
    except Exception as e:
        logger.debug(f"Could not compute font em ratio for {clean_family}: {e}")

    return 0.72

