"""Smoke test for app server, routes, and API methods."""

import os
import pytest
from piccut.app import create_server
from piccut.api import AppApi

def test_app_server_routes():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gui_dir = os.path.join(base_dir, "piccut", "gui")
    app = create_server(gui_dir)

    # Test index route
    req_env = {"REQUEST_METHOD": "GET", "PATH_INFO": "/"}
    resp = app(req_env, lambda status, headers, exc_info=None: None)
    body = b"".join(resp).decode("utf-8")
    assert "CHLACA" in body
    assert "subtitleOverlay" in body
    assert "Media & Transcribe" in body
    assert "nav-tab" in body

def test_api_state_and_methods():
    api = AppApi(server_port=8765)
    init_data = api.get_init_data()
    assert "models" in init_data
    assert "devices" in init_data
    assert "fonts" in init_data
    assert len(init_data["fonts"]) > 10
    assert "Montserrat" in init_data["fonts"]

    # Test loading video
    test_video = "tests/fixtures/test_vertical_short.mp4"
    if os.path.isfile(test_video):
        res = api.load_video(test_video)
        assert res["success"] is True
        assert res["info"]["is_vertical"] is True

        # Test updating style with background box and highlight toggle
        new_style = {
            "font_family": "Impact",
            "font_size": 80,
            "front_color": "#FFFFFF",
            "back_color": "#000000",
            "enable_background_box": True,
            "background_color": "#000000",
            "background_alpha": 180,
            "enable_highlight": False,
            "vertical_position_pct": 70.0
        }
        style_res = api.update_style(new_style)
        assert style_res["success"] is True
        assert style_res["style"]["enable_background_box"] is True
        assert style_res["style"]["enable_highlight"] is False
        assert style_res["style"]["font_family"] == "Impact"
