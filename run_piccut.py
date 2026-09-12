#!/usr/bin/env python
"""PicCut: Lightweight Desktop App for Animated Subtitles on Vertical YouTube Shorts.
Usage:
    python run_piccut.py
"""

import sys
import os

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from piccut.app import run_app

if __name__ == "__main__":
    debug_mode = "--debug" in sys.argv
    run_app(debug=debug_mode)
