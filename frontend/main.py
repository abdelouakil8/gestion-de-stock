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
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import (
        QApplication,
        QMessageBox,
        QProxyStyle,
        QStyle,
        QStyleOption,
        QStyleOptionComplex,
    )

    from app.core.config import settings
    from services.api_client import ApiClient, ApiError
    from services.updater import CURRENT_VERSION
    from ui import strings
    from ui.styles import tokens
    from ui.styles.tokens import render_qss
except Exception:
    _crash_log("import")
    raise

DEFAULT_STORE_NAME = "Ma Boutique"

def _parse_semver(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.lstrip("v").split(".") if p.isdigit())

def start_api_server() -> uvicorn.Server:
    """Run uvicorn on a daemon thread inside this same process."""
    from app.main import app as fastapi_app
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


def _check_license() -> bool:
    """Verify the offline license once, before the app opens.

    Shows a French error dialog and returns False when the license is
    missing, tampered, or expired (``verify_license`` raises ``ValueError``
    on an expired or invalid license). Returns True when the app may proceed.
    """
    from services.license import find_license, verify_license

    lic_path = find_license()
    if not lic_path:
        QMessageBox.critical(None, strings.LICENSE_ERROR_TITLE, strings.LICENSE_MISSING)
        return False
    try:
        verify_license(lic_path)
    except ValueError as e:
        QMessageBox.critical(None, strings.LICENSE_ERROR_TITLE, str(e))
        return False
    return True


def _theme_from_settings(store_settings: dict) -> tuple[str, str, dict]:
    """(accent, mode, overrides) from a settings payload, dropping blanks."""
    overrides = {
        "background": store_settings.get("theme_bg"),
        "surface": store_settings.get("theme_surface"),
        "text": store_settings.get("theme_text"),
        "border": store_settings.get("theme_border"),
    }
    return (
        store_settings.get("theme_accent") or "#2563EB",
        store_settings.get("theme_mode") or "light",
        {role: value for role, value in overrides.items() if value},
    )


class NoFocusProxyStyle(QProxyStyle):
    """A proxy style that completely disables native focus rectangles.

    QSS `outline: none` does not reliably suppress the native focus rect.
    Intercepting PE_FrameFocusRect works for some widgets, but QCheckBox and
    others use CE_CheckBoxLabel which natively draws the focus rect. We strip
    the focus state entirely before the native engine paints, ensuring no OS
    focus boxes are ever drawn (our QSS handles focus visibility).
    """

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget=None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_FrameFocusRect:
            return  # Do nothing
        super().drawPrimitive(element, option, painter, widget)

    def drawControl(
        self,
        element: QStyle.ControlElement,
        option: QStyleOption,
        painter: QPainter,
        widget=None,
    ) -> None:
        if option and (option.state & QStyle.StateFlag.State_HasFocus):
            # Strip focus state so native engine never paints its focus visuals
            option.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawControl(element, option, painter, widget)

    def drawComplexControl(
        self,
        element: QStyle.ComplexControl,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget=None,
    ) -> None:
        if option and (option.state & QStyle.StateFlag.State_HasFocus):
            option.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawComplexControl(element, option, painter, widget)


def _apply_theme(qt_app: QApplication, accent=None, mode=None, overrides=None) -> None:
    """Apply the full theme: Fusion base, the QSS, and a matching QPalette.

    The palette is derived from the SAME theme as the stylesheet, so the OS
    light/dark palette can never bleed through a widget the QSS doesn't paint
    (that was the solid-black dialog background). Works for light AND dark.
    """
    qt_app.setStyle("Fusion")
    qt_app.setStyle(NoFocusProxyStyle(qt_app.style()))
    qt_app.setStyleSheet(render_qss(accent, mode, overrides))
    qt_app.setPalette(tokens.build_palette())


def main() -> int:
    qt_app = QApplication(sys.argv)
    _install_qt_exception_guard()
    qt_app.setApplicationName(strings.APP_TITLE)
    
    from PySide6.QtWidgets import QSplashScreen
    from PySide6.QtGui import QPixmap, QColor
    pixmap = QPixmap(500, 350)
    pixmap.fill(QColor("#2563EB"))  # Primary accent color
    splash = QSplashScreen(pixmap)
    splash.showMessage(
        "Chargement de GestionStock...", 
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, 
        Qt.GlobalColor.white
    )
    splash.show()
    qt_app.processEvents()

    server = start_api_server()

    _apply_theme(qt_app)  # default theme until the store's settings load
    qt_app.aboutToQuit.connect(lambda: setattr(server, "should_exit", True))

    # Dev toggle to verify RTL mirroring before the Arabic language update.
    if os.environ.get("POS_FORCE_RTL"):
        qt_app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    smoke_test = bool(os.environ.get("POS_SMOKE_TEST"))

    # License gate: the interactive app verifies exactly once, before any real
    # work. Automated smoke tests (POS_SMOKE_TEST) skip it entirely.
    if not smoke_test and not _check_license():
        return 1

    if not wait_for_api():
        QMessageBox.critical(
            None, strings.API_STARTUP_ERROR_TITLE, strings.API_STARTUP_ERROR_TEXT
        )
        return 1

    api = ApiClient(settings.api_host, settings.api_port)

    try:
        ver = api.check_version()
        min_fe = ver.get("min_frontend_version", "0.0.0")
        if _parse_semver(CURRENT_VERSION) < _parse_semver(min_fe):
            QMessageBox.critical(
                None,
                strings.VERSION_MISMATCH_TITLE,
                strings.VERSION_MISMATCH_TEXT.format(
                    frontend=CURRENT_VERSION,
                    api=ver.get("api_version", "?"),
                    min_fe=min_fe,
                ),
            )
            return 1
    except ApiError:
        pass

    try:
        store = bootstrap_store(api)
    except ApiError as exc:
        QMessageBox.critical(None, strings.ERROR_TITLE, exc.message)
        return 1

    # Theme accent comes from the store settings (Réglages). Startup-only
    # blocking call, pre-UI; a failure just keeps the default accent.
    try:
        store_settings = api.get_settings(store["id"])
        accent, mode, overrides = _theme_from_settings(store_settings)
        _apply_theme(qt_app, accent, mode, overrides)

        from ui.i18n import apply_language

        apply_language(store_settings.get("ui_language", "fr"))
    except Exception as exc:
        logger.warning("Failed to fetch settings at startup: {}", exc)

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
        # Always show the login gate (multi-user): the operator picks their
        # name and PIN and receives a session token. On a just-configured
        # install the owner is materialized from the PIN and is pickable.
        from ui.screens.login import LoginDialog
        login = LoginDialog(api)
        if not login.exec():
            return 0

    logger.info(
        "UI started | store_id={} rtl={}",
        store["id"],
        bool(os.environ.get("POS_FORCE_RTL")),
    )

    # Building the shell takes a moment on old hardware — show a busy cursor
    # instead of a dead gap between the PIN dialog and the window.
    qt_app.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        from ui.screens.main_window import MainWindow
        window = MainWindow(api, store)
        window.show()
    finally:
        qt_app.restoreOverrideCursor()
        splash.finish(window)

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
