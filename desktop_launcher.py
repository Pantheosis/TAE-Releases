"""
desktop_launcher.py
Packages app.py (the Traditional Astrology Engine) as a native desktop window
using pywebview, with Streamlit running as a local, headless subprocess.

DEV MODE (no packaging, just testing the desktop shell):
    pip install pywebview
    python desktop_launcher.py

PACKAGED MODE:
    Build with `pyinstaller build.spec`. Must be run separately ON Windows
    (produces a .exe) and ON macOS (produces a .app) -- PyInstaller does not
    cross-compile between platforms. See BUILD_NOTES.md.

HOW THIS WORKS INSIDE A FROZEN (PyInstaller) BUILD:
A frozen build has no separate `python`/`streamlit` binary to shell out to --
the interpreter and this script are merged into one executable. So instead,
this same executable re-invokes ITSELF (via sys.executable, which points at
the frozen exe/app itself once packaged) with a hidden sentinel flag. That
child process detects the flag and runs Streamlit's CLI in-process instead
of opening a window. The parent process waits for that server to come up,
then opens a pywebview window pointed at it.
"""

import os
import sys
import socket
import subprocess
import time
import threading
import atexit
import logging

import webview

# Sentinel argument that tells a re-invocation of this executable to act as
# the Streamlit server rather than opening the desktop window.
_SERVER_SENTINEL = "--run-streamlit-server"

APP_TITLE = "Traditional Astrology Engine"
WINDOW_SIZE = (1400, 900)
WINDOW_MIN_SIZE = (900, 600)


def _resource_path(relative_path: str) -> str:
    """Resolve a bundled data file's path, both in dev and when frozen by
    PyInstaller (which unpacks --add-data files under sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def _free_port() -> int:
    """Ask the OS for an unused local port rather than hardcoding one, so a
    port left busy by a leftover process (or a second instance) never
    causes a silent failure."""
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
    """Entry point used when this executable is re-invoked with the
    sentinel flag: this process BECOMES the Streamlit server."""
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    # No source file to watch/hot-reload inside a frozen build, and the
    # watcher can raise errors in that environment -- disable it.
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

    try:
        from streamlit.web import cli as stcli
    except ImportError:
        # Fallback for older Streamlit versions.
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
    """Build the command to re-invoke this program as the Streamlit server.

    In a FROZEN build, sys.executable IS this program -- [sys.executable,
    sentinel, port] is correct on its own.

    In DEV mode, sys.executable is just the raw Python interpreter, which
    doesn't know to run this script unless we explicitly pass its path as
    an argument -- omitting that (as an earlier version of this file did)
    causes Python to receive "--run-streamlit-server" as its own argument,
    exit immediately, and the server never starts (surfacing as the
    "did not start within the timeout" error with no visible cause,
    since stdout/stderr were suppressed)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, _SERVER_SENTINEL, port]
    return [sys.executable, os.path.abspath(__file__), _SERVER_SENTINEL, port]


def _launch_desktop_window():
    """Normal entry point: spawn a private Streamlit server (by
    re-invoking this executable with the sentinel flag) and point a native
    pywebview window at it."""
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

    # Read the child's output in the background instead of DEVNULL-ing it,
    # so a failure can be diagnosed immediately without editing this file.
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

    # Log pywebview's own internal diagnostic messages to a file next to the
    # executable. With console=False (a windowed build), stdout/stderr
    # aren't available, so without this, pywebview's logger.exception(...)
    # calls when a backend fails to load are silently discarded -- leaving
    # us unable to see WHY, only that something eventually crashed.
    log_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    try:
        logging.basicConfig(
            filename=os.path.join(log_dir, "webview_debug.log"),
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        )
    except OSError:
        pass  # if the directory isn't writable, proceed without a log file

    webview.create_window(
        APP_TITLE, url,
        width=WINDOW_SIZE[0], height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
    )

    if sys.platform == "win32":
        # pywebview's legacy WinForms + Internet Explorer/MSHTML renderer is
        # meant purely as a last-resort fallback -- but on any modern
        # Windows install with no IE registry traces left (now the norm),
        # it crashes with an uncaught FileNotFoundError instead of failing
        # gracefully (pywebview's own probing only catches ImportError
        # around this, not the OSError this raises). Forcing gui=
        # "edgechromium" alone does NOT prevent this fallback -- pywebview's
        # own changelog documents WinForms fallback as intentional even
        # when a different backend was explicitly requested. Since we
        # always want the modern EdgeChromium/WebView2 backend anyway,
        # disable the WinForms candidate entirely: if EdgeChromium also
        # fails, this now surfaces as a single clean WebViewException
        # instead of a crash three modules deep, and the real underlying
        # reason EdgeChromium failed will be in webview_debug.log.
        import webview.guilib as _guilib
        _guilib.import_winforms = lambda: False

    gui_backend = "edgechromium" if sys.platform == "win32" else None
    webview.start(gui=gui_backend)

    # Window closed -> tear down the server subprocess.
    proc.terminate()


if __name__ == "__main__":
    if _SERVER_SENTINEL in sys.argv:
        _run_as_streamlit_server(sys.argv[sys.argv.index(_SERVER_SENTINEL) + 1])
    else:
        _launch_desktop_window()
