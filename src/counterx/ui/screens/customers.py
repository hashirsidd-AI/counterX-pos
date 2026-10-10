"""Customers directory screen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from ... import models
from ..base import BaseScreen
from ..theme import set_class


class CustomerDialog(QDialog):
    """Add / edit a customer (name required)."""

    def __init__(self, screen: "CustomersScreen", customer_id: int | None = None):
        super().__init__(screen)
        self._screen = screen
        self._customer_id = customer_id
        self.setWindowTitle("Edit Customer" if customer_id else "Add Customer")
        self.setModal(True)
        self.setMinimumWidth(420)

        form = QFormLayout(self)
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.phone.setPlaceholderText("03xx-xxxxxxx")
        self.address = QLineEdit()
        self.notes = QTextEdit()
        self.notes.setMaximumHeight(70)
        form.addRow("Name *:", self.name)
        form.addRow("Phone:", self.phone)
        form.addRow("Address:", self.address)
        form.addRow("Notes:", self.notes)

        if customer_id is not None:
            self._load(customer_id)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _load(self, customer_id: int) -> None:
        with self._screen.db() as s:
            c = s.get(models.Customer, customer_id)
            if c is None:
                return
            data = dict(name=c.name, phone=c.phone or "",
                        address=c.address or "", notes=c.notes or "")
        self.name.setText(data["name"])
        self.phone.setText(data["phone"])
        self.address.setText(data["address"])
        self.notes.setPlainText(data["notes"])

    def _save(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.name.setFocus()
            return
        payload = dict(name=name,
                       phone=self.phone.text().strip(),
                       address=self.address.text().strip(),
                       notes=self.notes.toPlainText().strip())

        def do() -> bool:
            with self._screen.db() as s:
                svc = self._screen.svc(s)
                actor = self._screen.ctx.actor(s)
                if self._customer_id is None:
                    svc.directory.create_customer(actor, **payload)
                else:
                    svc.directory.update_customer(actor, self._customer_id,
                                                  **payload)
            return True

        if self._screen.safe(do):
            self.accept()


class CustomersScreen(BaseScreen):
    nav_title = "Customers"
    nav_permission = "sell"
    nav_order = 70

    # -- UI -------------------------------------------------------------------
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Customers")
        set_class(title, "h1")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or phone…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search, 2)

        self.add_btn = QPushButton("Add")
        set_class(self.add_btn, "primary")
        self.add_btn.clicked.connect(self._add)
        toolbar.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._edit)
        toolbar.addWidget(self.edit_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Phone", "Address", "Notes"])
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # defense in depth: service layer still enforces these
        self.gate(self.add_btn, "sell")
        self.gate(self.edit_btn, "sell")

    def on_show(self) -> None:
        self.refresh()

    # -- data -------------------------------------------------------------------
    def refresh(self) -> None:
        query = self.search.text()
        with self.db() as s:
            rows = [(c.id, c.name, c.phone or "", c.address or "",
                     c.notes or "")
                    for c in self.svc(s).directory.list_customers(query)]
        self.table.setRowCount(0)
        for cid, name, phone, address, notes in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            id_item = QTableWidgetItem(name)
            id_item.setData(Qt.ItemDataRole.UserRole, cid)
            self.table.setItem(r, 0, id_item)
            self.table.setItem(r, 1, QTableWidgetItem(phone))
            self.table.setItem(r, 2, QTableWidgetItem(address))
            self.table.setItem(r, 3, QTableWidgetItem(notes))
        self.table.resizeColumnsToContents()

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # -- actions ------------------------------------------------------------------
    def _add(self) -> None:
        if CustomerDialog(self).exec():
            self.refresh()

    def _edit(self) -> None:
        cid = self._selected_id()
        if cid is None:
            self.warn("Select a customer first.")
            return
        if CustomerDialog(self, customer_id=cid).exec():
            self.refresh()
