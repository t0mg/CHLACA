"""Style preset management for PicCut.
Provides built-in presets tailored for YouTube Shorts and persists custom user presets
to ~/.piccut/presets.json.
"""

import os
import json
import copy
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_PRESETS: Dict[str, Dict[str, Any]] = {
    "Default Shorts": {
        "name": "Default Shorts",
        "font_family": "Montserrat",
        "font_size": 68,
        "font_weight": 800,
        "front_color": "#FFFFFF",
        "back_color": "#000000",
        "outline_width": 0.0,
        "shadow_depth": 2.0,
        "enable_background_box": False,
        "background_color": "#000000",
        "background_alpha": 89,
        "enable_highlight": True,
        "highlight_font": "Montserrat",
        "highlight_size": 72,
        "highlight_size_delta": 4,
        "highlight_front_color": "#FFE600",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 72.0,
        "enable_pop_effect": True,
        "is_builtin": True
    },
    "Syne ExtraBold Box": {
        "name": "Syne ExtraBold Box",
        "font_family": "Syne",
        "font_size": 68,
        "font_weight": 800,
        "front_color": "#FFFFFF",
        "back_color": "#000000",
        "outline_width": 0.0,
        "shadow_depth": 2.0,
        "enable_background_box": True,
        "background_color": "#000000",
        "background_alpha": 89,
        "enable_highlight": True,
        "highlight_font": "Syne",
        "highlight_size": 68,
        "highlight_size_delta": 0,
        "highlight_front_color": "#FFE600",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 72.0,
        "enable_pop_effect": True,
        "is_builtin": True
    },
    "Neon Green Stroke": {
        "name": "Neon Green Stroke",
        "font_family": "Anton",
        "font_size": 72,
        "font_weight": 800,
        "front_color": "#FFFFFF",
        "back_color": "#000000",
        "outline_width": 3.0,
        "shadow_depth": 2.0,
        "enable_background_box": False,
        "background_color": "#000000",
        "background_alpha": 89,
        "enable_highlight": True,
        "highlight_font": "Anton",
        "highlight_size": 76,
        "highlight_size_delta": 4,
        "highlight_front_color": "#00FF66",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 72.0,
        "enable_pop_effect": True,
        "is_builtin": True
    },
    "Cyber Cyan Box": {
        "name": "Cyber Cyan Box",
        "font_family": "Montserrat",
        "font_size": 68,
        "font_weight": 800,
        "front_color": "#FFFFFF",
        "back_color": "#000000",
        "outline_width": 1.5,
        "shadow_depth": 2.0,
        "enable_background_box": True,
        "background_color": "#070E18",
        "background_alpha": 75,
        "enable_highlight": True,
        "highlight_font": "Montserrat",
        "highlight_size": 72,
        "highlight_size_delta": 4,
        "highlight_front_color": "#00E5FF",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 72.0,
        "enable_pop_effect": True,
        "is_builtin": True
    },
    "Clean Minimal": {
        "name": "Clean Minimal",
        "font_family": "Roboto",
        "font_size": 60,
        "font_weight": 600,
        "front_color": "#FFFFFF",
        "back_color": "#000000",
        "outline_width": 0.0,
        "shadow_depth": 1.5,
        "enable_background_box": True,
        "background_color": "#000000",
        "background_alpha": 89,
        "enable_highlight": True,
        "highlight_font": "Roboto",
        "highlight_size": 62,
        "highlight_size_delta": 2,
        "highlight_front_color": "#FFE600",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 72.0,
        "enable_pop_effect": False,
        "is_builtin": True
    }
}

def get_presets_file_path() -> str:
    """Return the absolute path to the presets.json file."""
    base_dir = os.path.join(os.path.expanduser("~"), ".piccut")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "presets.json")

def load_presets() -> Dict[str, Dict[str, Any]]:
    """Load all style presets (built-in + user saved from ~/.piccut/presets.json)."""
    presets = copy.deepcopy(DEFAULT_PRESETS)
    file_path = get_presets_file_path()
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k, v in saved.items():
                    if isinstance(v, dict):
                        v["name"] = k
                        v["is_builtin"] = False
                        presets[k] = v
        except Exception as e:
            logger.warning(f"Failed to load user presets from {file_path}: {e}")
    return presets

def save_custom_preset(name: str, style_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Save or overwrite a user custom preset in ~/.piccut/presets.json."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Preset name cannot be empty")

    file_path = get_presets_file_path()
    saved: Dict[str, Any] = {}
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if not isinstance(saved, dict):
                saved = {}
        except Exception:
            saved = {}

    preset_copy = copy.deepcopy(style_dict)
    preset_copy["name"] = clean_name
    preset_copy["is_builtin"] = False
    saved[clean_name] = preset_copy

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(saved, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved custom preset '{clean_name}' to {file_path}")
    return load_presets()

def delete_custom_preset(name: str) -> Dict[str, Any]:
    """Delete a user custom preset from ~/.piccut/presets.json."""
    clean_name = name.strip()
    file_path = get_presets_file_path()
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict) and clean_name in saved:
                del saved[clean_name]
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(saved, f, indent=2, ensure_ascii=False)
                logger.info(f"Deleted custom preset '{clean_name}'")
        except Exception as e:
            logger.warning(f"Failed to delete preset '{clean_name}': {e}")
    return load_presets()
