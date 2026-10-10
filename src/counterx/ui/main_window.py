"""Main application window: navy sidebar navigation + light workspace."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from ..config import APP_NAME
from .base import AppContext, get_setting
from .screens import SCREENS
from .theme import set_class

# Sidebar navigation grouped by area. Titles must match each screen's
# nav_title; anything not listed here falls back to nav_order sorting.
NAV_GROUPS: list[tuple[str, list[str]]] = [
    ("SALES", ["Dashboard", "New Sale", "Orders & History"]),
    ("CATALOG", ["Products & Menu", "Categories & Modifiers",
                 "Inventory & Stock", "Purchases", "Suppliers"]),
    ("CASH", ["Cash Register", "Shift Management", "Day Closing", "Expenses"]),
    ("MANAGE", ["Customers", "Employees & Permissions", "Reports & Analytics"]),
    ("SYSTEM", ["Printer Settings", "Business Settings", "Database & Backup",
                "Cloud Sync", "License & About"]),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- sidebar ---------------------------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 16, 12, 12)
        side_layout.setSpacing(4)

        brand = QLabel("◆ CounterX")
        set_class(brand, "brand")
        brand_sub = QLabel("POS SOFTWARE COMPANY")
        set_class(brand_sub, "brand-sub")
        side_layout.addWidget(brand)
        side_layout.addWidget(brand_sub)
        side_layout.addSpacing(12)

        nav_area = QScrollArea()
        nav_area.setWidgetResizable(True)
        nav_area.setFrameShape(QScrollArea.Shape.NoFrame)
        nav_area.setStyleSheet("QScrollArea, QWidget#NavHost { background: #14243A; }")
        nav_host = QWidget()
        nav_host.setObjectName("NavHost")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(2)

        self.stack = QStackedWidget()
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.screens: dict[str, object] = {}

        visible = [c for c in sorted(SCREENS, key=lambda c: c.nav_order)
                   if ctx.can(c.nav_permission)]
        by_title = {c.nav_title: c for c in visible}
        for section, titles in NAV_GROUPS:
            section_added = False
            for title in titles:
                cls = by_title.pop(title, None)
                if cls is None:
                    continue
                if not section_added:
                    header = QLabel(section)
                    set_class(header, "nav-section")
                    nav_layout.addWidget(header)
                    section_added = True
                self._add_nav_button(cls, nav_layout)
        # Any screen not listed in NAV_GROUPS (fallback: nav_order).
        for cls in sorted(by_title.values(), key=lambda c: c.nav_order):
            self._add_nav_button(cls, nav_layout)
        nav_layout.addStretch(1)
        nav_area.setWidget(nav_host)
        side_layout.addWidget(nav_area, 1)

        user_lbl = QLabel(f"{ctx.username} ({ctx.role})")
        user_lbl.setStyleSheet("color: #9FB0C7;")
        side_layout.addWidget(user_lbl)
        root.addWidget(sidebar)

        # ---- workspace ---------------------------------------------------------
        work = QWidget()
        work_layout = QVBoxLayout(work)
        work_layout.setContentsMargins(20, 16, 20, 16)
        work_layout.addWidget(self.stack, 1)
        root.addWidget(work, 1)

        # ---- status bar ----------------------------------------------------------
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.shift_label = QLabel()
        self.day_label = QLabel()
        self.status.addPermanentWidget(self.shift_label)
        self.status.addPermanentWidget(self.day_label)

        if visible:
            first_btn = self.nav_group.buttons()[0]
            first_btn.setChecked(True)
            self.show_screen(0)
        self.refresh_chrome()

    def _add_nav_button(self, cls, nav_layout) -> None:
        """Instantiate one screen and add its sidebar button."""
        screen = cls(self.ctx)
        idx = self.stack.addWidget(screen)
        self.screens[cls.nav_title] = screen
        btn = QPushButton(cls.nav_title)
        btn.setObjectName("NavButton")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _=False, i=idx: self.show_screen(i))
        self.nav_group.addButton(btn)
        nav_layout.addWidget(btn)
        screen._nav_index = idx  # noqa: SLF001

    def show_screen(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        widget = self.stack.widget(index)
        if hasattr(widget, "on_show"):
            widget.on_show()

    def refresh_chrome(self) -> None:
        """Update window title + status bar from the real database."""
        try:
            with self.ctx.engine.connect() as _:
                pass
            from ..database import session_scope
            with session_scope(self.ctx.engine) as s:
                from ..services import ShiftService, AuthService
                auth = AuthService(s)
                svc = ShiftService(s, auth)
                shift = svc.current_shift()
                business_name = get_setting(s, "business_name", "") or APP_NAME
                self.setWindowTitle(f"{business_name} — {APP_NAME}")
                if shift:
                    self.shift_label.setText(
                        f"Shift #{shift.id} OPEN (opened "
                        f"{shift.opened_at:%d-%m %H:%M})")
                else:
                    self.shift_label.setText("No shift open")
                self.day_label.setText(
                    f"Business day: {datetime.now():%d-%m-%Y}")
        except Exception:  # noqa: BLE001
            self.shift_label.setText("Shift: unknown")
