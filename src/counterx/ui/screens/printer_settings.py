"""Printer Settings screen: choose receipt / KOT printers and test-print."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ...config import COMPANY_NAME, COMPANY_PHONES
from .. import printing_ui
from ..base import BaseScreen, get_setting, set_setting
from ..theme import set_class


def _sample_receipt() -> str:
    """A 42-column test receipt."""
    line = "-" * 42
    body = [
        line,
        "TEST PRINT".center(42),
        f"{COMPANY_NAME}".center(42),
        ", ".join(COMPANY_PHONES).center(42),
        line,
        "Item                          Qty   Amount",
        line,
        "Test Item                       1  Rs 100.00",
        line,
        "TOTAL:                          Rs 100.00",
        line,
        "If you can read this, the printer works.".center(42),
        "Thank you!".center(42),
        line,
    ]
    return "\n".join(body) + "\n"


class PrinterSettingsScreen(BaseScreen):
    nav_title = "Printer Settings"
    nav_permission = "settings"
    nav_order = 160

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Printer Settings")
        set_class(title, "h1")
        layout.addWidget(title)

        form = QFormLayout()
        self.receipt_combo = QComboBox()
        self.receipt_combo.setEditable(True)
        self.kot_combo = QComboBox()
        self.kot_combo.setEditable(True)
        form.addRow("Receipt printer:", self.receipt_combo)
        form.addRow("KOT printer:", self.kot_combo)
        layout.addLayout(form)

        bar = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        set_class(self.save_btn, "primary")
        self.save_btn.clicked.connect(self._save)
        self.test_btn = QPushButton("Test Print")
        self.test_btn.clicked.connect(self._test_print)
        bar.addWidget(self.save_btn)
        bar.addWidget(self.test_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        note = QLabel(
            "Thermal receipt printers are configured on the Windows build. "
            "On this machine, printing may fall back to saving a text file — "
            "the result message will tell you exactly where it went.")
        set_class(note, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def on_show(self) -> None:
        def _do(s):
            return {
                "receipt": get_setting(s, "receipt_printer", ""),
                "kot": get_setting(s, "kot_printer", ""),
            }

        with self.db() as s:
            saved = self.safe(_do, s)
        if saved is None:
            return
        printers = printing_ui.list_printers()
        for combo, value in ((self.receipt_combo, saved["receipt"]),
                             (self.kot_combo, saved["kot"])):
            combo.clear()
            items = list(printers)
            if value and value not in items:
                items.insert(0, value)
            combo.addItems(items)
            combo.setCurrentText(value)

    # -- actions ----------------------------------------------------------------
    def _save(self) -> None:
        receipt = self.receipt_combo.currentText().strip()
        kot = self.kot_combo.currentText().strip()

        def _do(s):
            set_setting(s, "receipt_printer", receipt)
            set_setting(s, "kot_printer", kot)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Printer settings saved.")

    def _test_print(self) -> None:
        printer = self.receipt_combo.currentText().strip()

        def _do(s):
            return printing_ui.print_text(_sample_receipt(), printer)

        with self.db() as s:
            result = self.safe(_do, s)
        if result is None:
            return
        ok, msg = result
        if ok:
            self.info(msg, title="Test Print")
        else:
            self.warn(msg, title="Test Print")
