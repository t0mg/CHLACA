import os
import json
import pytest
from piccut.presets import (
    load_presets,
    save_custom_preset,
    delete_custom_preset,
    DEFAULT_PRESETS,
    get_presets_file_path
)
from piccut.api import AppApi

def test_load_default_presets():
    presets = load_presets()
    assert len(presets) >= 5
    assert "Default Shorts" in presets
    assert "Syne ExtraBold Box" in presets
    assert "Neon Green Stroke" in presets
    assert "Cyber Cyan Box" in presets
    assert "Clean Minimal" in presets
    assert presets["Default Shorts"]["is_builtin"] is True
    assert presets["Syne ExtraBold Box"]["font_family"] == "Syne"
    assert presets["Syne ExtraBold Box"]["enable_background_box"] is True

def test_save_and_delete_custom_preset(tmp_path, monkeypatch):
    # Route presets file to tmp_path
    tmp_file = str(tmp_path / "test_presets.json")
    monkeypatch.setattr("piccut.presets.get_presets_file_path", lambda: tmp_file)

    custom_style = {
        "font_family": "Montserrat",
        "font_size": 75,
        "font_weight": 800,
        "front_color": "#FFFF00",
        "back_color": "#000000",
        "outline_width": 2.0,
        "enable_background_box": True,
        "background_color": "#111111",
        "background_alpha": 120,
        "enable_highlight": True,
        "highlight_font": "Montserrat",
        "highlight_size": 78,
        "highlight_front_color": "#00FF00",
        "highlight_back_color": "#000000",
        "vertical_position_pct": 75.0,
        "enable_pop_effect": True
    }

    # Save
    updated = save_custom_preset("My Custom Brand", custom_style)
    assert "My Custom Brand" in updated
    assert updated["My Custom Brand"]["is_builtin"] is False
    assert updated["My Custom Brand"]["front_color"] == "#FFFF00"
    assert os.path.isfile(tmp_file)

    # Re-load from file
    reloaded = load_presets()
    assert "My Custom Brand" in reloaded
    assert reloaded["My Custom Brand"]["front_color"] == "#FFFF00"

    # Delete
    after_del = delete_custom_preset("My Custom Brand")
    assert "My Custom Brand" not in after_del
    assert "Default Shorts" in after_del

def test_save_preset_empty_name():
    with pytest.raises(ValueError):
        save_custom_preset("   ", {})

def test_app_api_preset_methods(tmp_path, monkeypatch):
    tmp_file = str(tmp_path / "api_presets.json")
    monkeypatch.setattr("piccut.presets.get_presets_file_path", lambda: tmp_file)

    api = AppApi()
    init_data = api.get_init_data()
    assert "presets" in init_data
    assert "Default Shorts" in init_data["presets"]

    # Save via API
    res_save = api.save_preset("API Brand Style", {"font_family": "Syne", "font_weight": 800})
    assert res_save["success"] is True
    assert "API Brand Style" in res_save["presets"]

    # Fetch via API
    res_get = api.get_presets()
    assert "API Brand Style" in res_get["presets"]

    # Delete via API
    res_del = api.delete_preset("API Brand Style")
    assert res_del["success"] is True
    assert "API Brand Style" not in res_del["presets"]
