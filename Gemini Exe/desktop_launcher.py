import os
import sys
import socket
import subprocess
import time
import threading
import atexit
import logging

import webview

_SERVER_SENTINEL = "--run-streamlit-server"

APP_TITLE = "Traditional Astrology Engine"
WINDOW_SIZE = (1400, 900)
WINDOW_MIN_SIZE = (900, 600)


def _resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 25.0) -> bool:
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.25)
    return False


def _run_as_streamlit_server(port: str):
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

    try:
        from streamlit.web import cli as stcli
    except ImportError:
        from streamlit import cli as stcli

    app_path = _resource_path("app.py")

    sys.argv = [
        "streamlit", "run", app_path,
        "--server.port", port,
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
        "--global.developmentMode", "false",
    ]
    sys.exit(stcli.main())


def _self_invoke_command(port: str) -> list:
    if getattr(sys, "frozen", False):
        return [sys.executable, _SERVER_SENTINEL, port]
    return [sys.executable, os.path.abspath(__file__), _SERVER_SENTINEL, port]


def _launch_desktop_window():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        _self_invoke_command(str(port)),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    atexit.register(proc.terminate)

    captured_lines = []

    def _drain_output():
        for line in proc.stdout:
            captured_lines.append(line.rstrip())

    reader_thread = threading.Thread(target=_drain_output, daemon=True)
    reader_thread.start()

    if not _wait_for_server(url):
        proc.terminate()
        reader_thread.join(timeout=2)
        server_output = "\n".join(captured_lines) or "(no output captured -- the process may have exited instantly)"
        raise RuntimeError(
            "The local Streamlit server did not start within the timeout.\n"
            "--- Captured server output ---\n"
            f"{server_output}\n"
            "-------------------------------"
        )

    log_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    try:
        logging.basicConfig(
            filename=os.path.join(log_dir, "webview_debug.log"),
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        )
    except OSError:
        pass

    webview.create_window(
        APP_TITLE, url,
        width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
    )

    # Force the Qt WebEngine backend, completely bypassing OS-level WebViews
    webview.start(gui="qt")

    proc.terminate()


if __name__ == "__main__":
    if _SERVER_SENTINEL in sys.argv:
        _run_as_streamlit_server(sys.argv[sys.argv.index(_SERVER_SENTINEL) + 1])
    else:
        _launch_desktop_window()
