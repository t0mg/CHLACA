"""💥CHLACA: cheap and lazy captions for vertical YouTube Shorts.
Usage:
    python run_chlaca.py
"""

import sys
import os

# Ensure package root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from piccut.app import run_app

if __name__ == "__main__":
    debug_mode = "--debug" in sys.argv
    run_app(debug=debug_mode)
