"""Desktop entrypoint.

Boots the local FastAPI service on a background thread (loopback only),
waits for it to become reachable, then shows the main window. The UI never
touches the database — every data operation goes through the local HTTP API.
"""

import os
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import httpx
import uvicorn
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import settings
from app.main import app as fastapi_app
from ui import strings
from ui.screens.main_window import MainWindow

STYLES_DIR = Path(__file__).resolve().parent / "ui" / "styles"


def start_api_server() -> uvicorn.Server:
    """Run uvicorn on a daemon thread inside this same process."""
    config = uvicorn.Config(
        fastapi_app,
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,  # logging is configured by the app itself (loguru)
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="local-api", daemon=True).start()
    return server


def wait_for_api(timeout_seconds: float = 15.0) -> bool:
    """Poll the liveness endpoint until the API answers or the timeout hits.

    Startup-only blocking wait: no window exists yet, so nothing freezes.
    Once the UI is up, every API call must go through a background worker.
    """
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.2)
    return False


def main() -> int:
    server = start_api_server()

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(strings.APP_TITLE)
    qt_app.setStyleSheet((STYLES_DIR / "app.qss").read_text(encoding="utf-8"))
    qt_app.aboutToQuit.connect(lambda: setattr(server, "should_exit", True))

    if not wait_for_api():
        QMessageBox.critical(
            None, strings.API_STARTUP_ERROR_TITLE, strings.API_STARTUP_ERROR_TEXT
        )
        return 1

    window = MainWindow()
    window.show()

    # Automated checks set POS_SMOKE_TEST to open and close the app unattended.
    if os.environ.get("POS_SMOKE_TEST"):
        QTimer.singleShot(3000, qt_app.quit)

    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
