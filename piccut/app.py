"""Main desktop application entry point for PicCut.
Runs a local streaming server and launches a native pywebview desktop window.
"""

import os
import sys
import logging
import threading
import bottle
import webview

from piccut.api import AppApi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("piccut")

def create_server(gui_dir: str):
    """Create a Bottle app to serve the GUI and stream local media with Range support."""
    app = bottle.Bottle()

    @app.route("/")
    def index():
        return bottle.static_file("index.html", root=gui_dir)

    @app.route("/static/<filepath:path>")
    def static_files(filepath):
        return bottle.static_file(filepath, root=gui_dir)

    @app.route("/stream-video")
    def stream_video():
        path = bottle.request.query.get("path")
        if not path or not os.path.isfile(path):
            bottle.response.status = 404
            return "File not found"

        file_dir = os.path.dirname(os.path.abspath(path))
        file_name = os.path.basename(path)
        # static_file in Bottle automatically handles HTTP 206 Partial Content (Range requests)
        return bottle.static_file(file_name, root=file_dir, mimetype="video/mp4")

    return app

def run_app(port: int = 8765, debug: bool = False):
    """Start local server and launch native desktop window."""
    if getattr(sys, "frozen", False):
        # Running in a PyInstaller bundle
        bundle_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        gui_dir = os.path.join(bundle_dir, "piccut", "gui")
        if not os.path.isdir(gui_dir):
            gui_dir = os.path.join(bundle_dir, "gui")
        # Ensure bundled ffmpeg/ffprobe binaries are discoverable in PATH
        exe_dir = os.path.dirname(sys.executable)
        os.environ["PATH"] = exe_dir + os.pathsep + bundle_dir + os.pathsep + os.environ.get("PATH", "")
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        gui_dir = os.path.join(base_dir, "gui")

    # Start bottle server in a background daemon thread
    server_app = create_server(gui_dir)
    server_thread = threading.Thread(
        target=lambda: bottle.run(server_app, host="127.0.0.1", port=port, quiet=True),
        daemon=True
    )
    server_thread.start()
    logger.info(f"Local streaming server running at http://127.0.0.1:{port}")

    # Create API instance
    api = AppApi(server_port=port)

    # Create desktop window
    window = webview.create_window(
        title="💥CHLACA - cheap and lazy captions",
        url=f"http://127.0.0.1:{port}/",
        js_api=api,
        width=1320,
        height=880,
        min_size=(1050, 720),
        text_select=True,
        background_color="#0F172A"
    )
    api.set_window(window)

    # Launch webview GUI loop
    logger.info("Launching desktop window...")
    webview.start(debug=debug)

def main():
    debug_mode = "--debug" in sys.argv
    run_app(debug=debug_mode)

if __name__ == "__main__":
    main()
