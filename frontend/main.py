"""Desktop entrypoint.

Boots the local FastAPI service on a background thread (loopback only),
waits for it to become reachable, gates the app behind the local PIN, then
shows the main window. The UI never touches the database — every data
operation goes through the local HTTP API, always from a worker thread once
the window exists (startup-only blocking happens before any UI is shown).
"""

import os
import sys
import threading
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


def _crash_log(stage: str) -> Path:
    """A packaged app must never die silently: dump the traceback where a
    technician can find it (%LOCALAPPDATA%/GestionStockPOS/logs/crash.log)."""
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GestionStockPOS"
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "crash.log"
    path.write_text(f"[{stage}]\n{traceback.format_exc()}", encoding="utf-8")
    return path


try:
    import httpx
    import uvicorn
    from loguru import logger
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.core.config import settings
    from app.main import app as fastapi_app
    from services.api_client import ApiClient, ApiError
    from ui import strings
    from ui.styles import tokens
    from ui.screens.login import LoginDialog
    from ui.screens.main_window import MainWindow
    from ui.styles.tokens import render_qss
except Exception:
    _crash_log("import")
    raise

DEFAULT_STORE_NAME = "Ma Boutique"


def start_api_server() -> uvicorn.Server:
    """Run uvicorn on a daemon thread inside this same process."""
    config = uvicorn.Config(
        fastapi_app,
        host=settings.api_host,  # loopback only — enforced in Settings
        port=settings.api_port,
        log_config=None,
    )
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name="local-api", daemon=True).start()
    return server


def wait_for_api(timeout_seconds: float = 20.0) -> bool:
    """Startup-only blocking wait: no window exists yet, nothing freezes."""
    base_url = f"http://{settings.api_host}:{settings.api_port}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/", timeout=1.0).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.2)
    return False


def bootstrap_store(api: ApiClient) -> dict:
    """First run: make sure one store exists (startup phase, pre-UI)."""
    stores = api.list_stores()
    if stores:
        return stores[0]
    return api.create_store(DEFAULT_STORE_NAME)


def _install_qt_exception_guard() -> None:
    """Keep the app alive when a Qt slot raises.

    PySide6 routes an unhandled exception from a signal/slot through
    sys.excepthook and, by default, aborts the process — the app just
    "closes suddenly" with no trace. Replace the hook so the traceback is
    logged (and shown once) but the event loop keeps running, the way a
    robust desktop app behaves. Real hard crashes (C++ use-after-free) are
    prevented at the source with shiboken validity guards in async callbacks.
    """
    import traceback as _tb

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        message = "".join(_tb.format_exception(exc_type, exc, tb))
        try:
            logger.error("Unhandled UI exception:\n{}", message)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication as _QApp

            if _QApp.instance() is not None:
                QMessageBox.critical(
                    None, strings.ERROR_TITLE, strings.UNEXPECTED_ERROR
                )
        except Exception:
            pass

    sys.excepthook = _hook


def main() -> int:
    server = start_api_server()

    qt_app = QApplication(sys.argv)
    _install_qt_exception_guard()
    qt_app.setApplicationName(strings.APP_TITLE)
    qt_app.setStyleSheet(render_qss())
    qt_app.aboutToQuit.connect(lambda: setattr(server, "should_exit", True))

    # Dev toggle to verify RTL mirroring before the Arabic language update.
    if os.environ.get("POS_FORCE_RTL"):
        qt_app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    from services.license import find_license, verify_license
    lic_path = find_license()
    if not lic_path:
        QMessageBox.critical(None, strings.LICENSE_ERROR_TITLE, strings.LICENSE_MISSING)
        return 1
    try:
        verify_license(lic_path)
    except ValueError as e:
        QMessageBox.critical(None, strings.LICENSE_ERROR_TITLE, str(e))
        return 1

    if not wait_for_api():
        QMessageBox.critical(
            None, strings.API_STARTUP_ERROR_TITLE, strings.API_STARTUP_ERROR_TEXT
        )
        return 1

    api = ApiClient(settings.api_host, settings.api_port)
    try:
        store = bootstrap_store(api)
    except ApiError as exc:
        QMessageBox.critical(None, strings.ERROR_TITLE, exc.message)
        return 1

    # Theme accent comes from the store settings (Réglages). Startup-only
    # blocking call, pre-UI; a failure just keeps the default accent.
    try:
        store_settings = api.get_settings(store["id"])
        tokens.CURRENT_ACCENT = store_settings.get("theme_accent", "#2563EB")
        
        from ui.i18n import apply_language
        apply_language(store_settings.get("ui_language", "fr"))
    except Exception as exc:
        logger.warning("Failed to fetch settings at startup: {}", exc)

    smoke_test = bool(os.environ.get("POS_SMOKE_TEST"))
    if not smoke_test:  # automated checks skip the interactive PIN gate
        # Check if PIN is configured safely without triggering a 401 warning
        try:
            status_data = api.get_auth_status()
            pin_configured = status_data.get("configured", True)
        except ApiError:
            pin_configured = True  # fallback if endpoint fails

        if not pin_configured:
            from ui.screens.onboarding import OnboardingWizard
            wizard = OnboardingWizard(api)
            if not wizard.exec():
                return 0
        else:
            login = LoginDialog(api)
            if not login.exec():
                return 0
                
    logger.info(
        "UI started | store_id={} rtl={}",
        store["id"],
        bool(os.environ.get("POS_FORCE_RTL")),
    )

    window = MainWindow(api, store)
    window.show()

    if smoke_test:
        QTimer.singleShot(4000, qt_app.quit)

    return qt_app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        _crash_log("runtime")
        raise
