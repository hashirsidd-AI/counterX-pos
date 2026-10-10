"""counterX POS — application entry point.

Flow: init DB -> first-run wizard (if no users) -> login -> main window.
Native desktop only; no browser involved at any point.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running from the source tree: <project>/src on sys.path.
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from counterx import models
from counterx.config import APP_NAME, APP_SLUG
from counterx.database import get_engine, init_db, session_scope
from counterx.sync import SyncService
from counterx.ui.base import AppContext
from counterx.ui.dialogs import FirstRunWizard, LoginDialog
from counterx.ui.main_window import MainWindow
from counterx.ui.theme import get_stylesheet

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("counterx.main")


def _app_icon() -> QIcon:
    for name in ("counterx.png", "counterx.ico"):
        p = SRC_DIR.parent / "assets" / name
        if p.exists():
            return QIcon(str(p))
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("counterX")
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(_app_icon())
    app.setStyleSheet(get_stylesheet())

    engine = get_engine()
    try:
        init_db(engine)
    except Exception:
        log.exception("Database initialization failed")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, APP_NAME,
                             "Could not initialize the local database.\n"
                             "The application cannot start.")
        return 1

    with session_scope(engine) as s:
        has_users = s.query(models.User).count() > 0

    user_id: int | None = None
    if not has_users:
        wiz = FirstRunWizard(engine)
        if wiz.exec() != wiz.DialogCode.Accepted or not wiz.user_id:
            return 0
        user_id = wiz.user_id
    else:
        while user_id is None:
            dlg = LoginDialog(engine)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return 0  # user cancelled -> quit
            user_id = dlg.user_id  # login only accepts on success

    ctx = AppContext(engine, user_id)
    try:
        ctx.refresh_identity()
    except Exception:
        log.exception("Failed to load user identity")
        return 1

    # Optional offline-first cloud sync: one shared service for the app.
    # Billing never depends on it; the worker only uploads when enabled.
    sync_service = SyncService(engine)
    try:
        with session_scope(engine) as s:
            sync_enabled = sync_service.get_state(s).sync_enabled
    except Exception:
        log.exception("Could not read sync state; sync worker not started")
        sync_enabled = False
    if sync_enabled:
        sync_service.start_worker()
        log.info("Cloud sync worker started (offline-first)")

    win = MainWindow(ctx)
    win.sync_service = sync_service  # kept alive for the app's lifetime
    win.show()
    log.info("counterX POS started for user %s", ctx.username)
    try:
        return app.exec()
    finally:
        sync_service.stop_worker()
        log.info("Cloud sync worker stopped")


if __name__ == "__main__":
    sys.exit(main())
