"""Suppliers screen: list, add, edit."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from ..base import BaseScreen
from ..theme import set_class


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class _SupplierDialog(QDialog):
    """Add / edit a supplier. Returns dict of fields or None."""

    def __init__(self, parent, title: str, initial: dict | None = None):
        super().__init__(parent)
        initial = initial or {}
        self.result: dict | None = None
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.name = QLineEdit(initial.get("name", ""))
        self.phone = QLineEdit(initial.get("phone", ""))
        self.address = QLineEdit(initial.get("address", ""))
        self.notes = QTextEdit(initial.get("notes", ""))
        self.notes.setMaximumHeight(80)
        layout.addRow("Name:", self.name)
        layout.addRow("Phone:", self.phone)
        layout.addRow("Address:", self.address)
        layout.addRow("Notes:", self.notes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._done)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _done(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        self.result = {
            "name": self.name.text().strip(),
            "phone": self.phone.text().strip(),
            "address": self.address.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }
        self.accept()


class SuppliersScreen(BaseScreen):
    nav_title = "Suppliers"
    nav_permission = "purchases"
    nav_order = 80

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Suppliers")
        set_class(title, "h1")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search suppliers (name / phone)...")
        self.search_box.returnPressed.connect(self.refresh)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        self.add_btn = QPushButton("Add Supplier")
        set_class(self.add_btn, "primary")
        self.add_btn.clicked.connect(self._add_supplier)
        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.clicked.connect(self._edit_supplier)
        self.gate(self.add_btn, "purchases")
        self.gate(self.edit_btn, "purchases")
        toolbar.addWidget(self.search_box, 1)
        toolbar.addWidget(search_btn)
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Phone", "Address", "Notes"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(lambda _item: self._edit_supplier())
        layout.addWidget(self.table, 1)

        self._rows: list[dict] = []

    def on_show(self) -> None:
        self.refresh()

    # -- data ------------------------------------------------------------------
    def refresh(self) -> None:
        query = self.search_box.text().strip()

        def load():
            with self.db() as s:
                svc = self.svc(s)
                return [{
                    "id": sp.id, "name": sp.name, "phone": sp.phone or "",
                    "address": sp.address or "", "notes": sp.notes or "",
                } for sp in svc.directory.list_suppliers(query)]

        rows = self.safe(load)
        if rows is None:
            return
        self._rows = rows
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, _cell(row["name"]))
            self.table.setItem(r, 1, _cell(row["phone"]))
            self.table.setItem(r, 2, _cell(row["address"]))
            self.table.setItem(r, 3, _cell(row["notes"]))
        self.table.resizeColumnsToContents()

    # -- actions -----------------------------------------------------------------
    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            self.warn("Select a supplier row first.")
            return None
        return self._rows[row]

    def _add_supplier(self) -> None:
        dlg = _SupplierDialog(self, "Add Supplier")
        if not (dlg.exec() and dlg.result):
            return
        fields = dlg.result

        def do():
            with self.db() as s:
                svc = self.svc(s)
                sp = svc.directory.create_supplier(self.ctx.actor(s), **fields)
                return sp.name

        name = self.safe(do)
        if name is not None:
            self.info(f"Supplier '{name}' added.")
            self.refresh()

    def _edit_supplier(self) -> None:
        row = self._selected()
        if not row:
            return
        dlg = _SupplierDialog(self, "Edit Supplier", initial=row)
        if not (dlg.exec() and dlg.result):
            return
        fields = dlg.result

        def do():
            with self.db() as s:
                svc = self.svc(s)
                sp = svc.directory.update_supplier(self.ctx.actor(s),
                                                   row["id"], **fields)
                return sp.name

        name = self.safe(do)
        if name is not None:
            self.info(f"Supplier '{name}' updated.")
            self.refresh()
