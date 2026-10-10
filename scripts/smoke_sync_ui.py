"""Offscreen smoke test for the cloud-sync UI additions.

Run: LD_LIBRARY_PATH=~/workspace/.qtlibs QT_QPA_PLATFORM=offscreen \
     .venv/bin/python scripts/smoke_sync_ui.py
Instantiates (does not show) the new/changed UI pieces against a temp DB.
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from counterx import database  # noqa: E402
from counterx.sync import SyncService  # noqa: E402

tmp = tempfile.mkdtemp()
engine = database.get_engine(os.path.join(tmp, "smoke.db"))
database.init_db(engine)

passed = []


def check(name, fn):
    try:
        fn()
        passed.append(name)
        print(f"{name}: PASS")
    except Exception as e:  # noqa: BLE001
        print(f"{name}: FAIL — {e}")
        raise SystemExit(1)


def _sync_screen():
    from counterx.ui.screens.sync import SyncScreen
    assert SyncScreen.nav_title == "Cloud Sync"
    assert SyncScreen.nav_permission == "settings"


def _dialogs():
    from counterx.ui.dialogs import (FirstRunWizard, LoginDialog,
                                     RecoveryDialog)
    w = FirstRunWizard(engine)
    assert w.business_type.count() == 4
    d = LoginDialog(engine)
    assert d is not None
    r = RecoveryDialog(engine)
    assert r is not None


def _main_window_builds():
    from counterx.ui.main_window import MainWindow
    # MainWindow needs an app context; just verify the class imports and
    # SCREENS registry includes the sync screen.
    from counterx.ui.screens import SCREENS
    titles = [c.nav_title for c in SCREENS]
    assert "Cloud Sync" in titles, titles
    assert len(titles) == 20, f"expected 20 screens, got {len(titles)}"


def _service_status():
    svc = SyncService(engine)
    with database.session_scope(engine) as s:
        st = svc.status(s)
    assert st["enabled"] is False
    assert st["pending"] == 0
    assert len(st["installation_id"]) == 36


check("SyncScreen registered (20 screens)", _main_window_builds)
check("SyncScreen contract", _sync_screen)
check("Wizard/Login/Recovery dialogs", _dialogs)
check("SyncService status on fresh DB", _service_status)
print(f"===== {len(passed)}/{len(passed)} passed =====")
