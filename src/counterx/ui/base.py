"""Shared UI contracts: AppContext, BaseScreen, settings helpers, guarded actions.

Every screen talks to the database through ``self.db()`` (a fresh
``session_scope`` per action) and builds services via ``self.svc(session)``.
Never share a SQLAlchemy session across widgets or threads.
"""
from __future__ import annotations

import logging
import traceback
from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox, QWidget

from .. import models
from ..config import APP_NAME
from ..database import session_scope
from ..services import (
    AuthService, BackupService, CatalogService, DirectoryService,
    InventoryService, LicenseService, PermissionDenied, PrintService,
    ReportService, SaleService, ShiftService,
)
from ..utils.money import fmt

log = logging.getLogger("counterx.ui")


# ---------------------------------------------------------------- settings ---
def get_setting(session, key: str, default: str = "") -> str:
    row = session.query(models.Setting).filter_by(key=key).first()
    return row.value if row and row.value is not None else default


def set_setting(session, key: str, value: str) -> None:
    row = session.query(models.Setting).filter_by(key=key).first()
    if row is None:
        session.add(models.Setting(key=key, value=value))
    else:
        row.value = value
    session.flush()


def make_services(session) -> SimpleNamespace:
    """Build every service bound to one session. Auth first (others need it)."""
    auth = AuthService(session)
    return SimpleNamespace(
        auth=auth,
        catalog=CatalogService(session, auth),
        sales=SaleService(session, auth),
        inventory=InventoryService(session, auth),
        shifts=ShiftService(session, auth),
        reports=ReportService(session),
        backup=BackupService(session, auth),
        licensing=LicenseService(session),
        printing=PrintService(session),
        directory=DirectoryService(session, auth),
    )


# ------------------------------------------------------------------ context ---
class AppContext:
    """Per-login state shared by the whole UI. Lightweight; never a session."""

    def __init__(self, engine, user_id: int):
        self.engine = engine
        self.user_id = user_id
        self.username = ""
        self.role = ""
        self.permissions: set[str] = set()
        self.business_name = ""

    def refresh_identity(self) -> None:
        with session_scope(self.engine) as s:
            auth = AuthService(s)
            user = s.get(models.User, self.user_id)
            if user is None:
                raise RuntimeError("Logged-in user no longer exists")
            self.username = user.username
            self.role = user.role
            self.permissions = set(auth.permissions_of(user))
            self.business_name = get_setting(s, "business_name", "")

    def actor(self, session) -> models.User:
        user = session.get(models.User, self.user_id)
        if user is None:
            raise RuntimeError("Logged-in user no longer exists")
        return user

    def can(self, permission: str | None) -> bool:
        if permission is None:
            return True
        return permission in self.permissions


# ------------------------------------------------------------------- screen ---
class BaseScreen(QWidget):
    """Base class for every module screen.

    Class attributes used by the main window for navigation:
        nav_title      - text shown in the sidebar
        nav_permission - permission required to SEE this screen (None = all)
        nav_order      - sidebar sort order
    """

    nav_title = ""
    nav_permission: str | None = None
    nav_order = 99

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.build_ui()

    # -- overridable -----------------------------------------------------------
    def build_ui(self) -> None:
        """Create widgets. Called once from __init__."""

    def on_show(self) -> None:
        """Refresh data. Called every time the screen becomes visible."""

    # -- data access ------------------------------------------------------------
    def db(self):
        """Fresh transactional session scope. Use as: ``with self.db() as s:``"""
        return session_scope(self.ctx.engine)

    def svc(self, session) -> SimpleNamespace:
        return make_services(session)

    # -- helpers ------------------------------------------------------------------
    def money(self, value) -> str:
        return fmt(value)

    def info(self, msg: str, title: str = APP_NAME) -> None:
        QMessageBox.information(self, title, msg)

    def warn(self, msg: str, title: str = APP_NAME) -> None:
        QMessageBox.warning(self, title, msg)

    def error(self, msg: str, title: str = APP_NAME) -> None:
        QMessageBox.critical(self, title, msg)

    def confirm(self, msg: str, title: str = "Please confirm") -> bool:
        return QMessageBox.question(
            self, title, msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def safe(self, fn, *args, **kwargs):
        """Run fn() translating service-layer errors into friendly messages.

        PermissionDenied is shown as 'not allowed' (services enforce, UI
        only hides). ValueError shows the message. Anything else is logged
        and shown generically. Returns fn()'s return value, or None on error.
        """
        try:
            return fn(*args, **kwargs)
        except PermissionDenied as e:
            self.warn(f"You are not allowed to do this.\n({e})")
        except ValueError as e:
            self.warn(str(e))
        except Exception:  # noqa: BLE001
            log.exception("Unhandled UI action error")
            self.error("An unexpected error occurred. Details were logged.\n"
                       + traceback.format_exc(limit=3))
        return None

    def gate(self, widget, permission: str) -> None:
        """Hide a widget the current user may not use (defense in depth;
        the service layer still enforces the permission)."""
        if not self.ctx.can(permission):
            widget.setVisible(False)
