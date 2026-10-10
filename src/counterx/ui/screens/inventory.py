"""Inventory & stock screen: levels, valuation, adjustments, ledger."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ...utils.money import d, fmt, q
from ..base import BaseScreen
from ..theme import set_class


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _qty_spin(min_value: float = -1_000_000.0,
              max_value: float = 1_000_000.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(min_value, max_value)
    spin.setDecimals(3)
    spin.setMinimumWidth(150)
    return spin


class _StockDialog(QDialog):
    """Generic stock move dialog. Returns (qty: Decimal, note: str) or None."""

    def __init__(self, parent, title: str, product_name: str,
                 allow_negative: bool, default_qty: float = 0.0):
        super().__init__(parent)
        self.result: tuple[Decimal, str] | None = None
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(400)
        layout = QFormLayout(self)
        layout.addRow("Product:", QLabel(product_name))
        lo = -1_000_000.0 if allow_negative else 0.0
        self.qty = _qty_spin(lo, 1_000_000.0)
        self.qty.setValue(default_qty)
        self.note = QLineEdit()
        self.note.setPlaceholderText("Note (optional)")
        layout.addRow("Quantity change:" if allow_negative else "Quantity:", self.qty)
        layout.addRow("Note:", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._done)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _done(self) -> None:
        self.result = (q(d(self.qty.value())), self.note.text().strip())
        self.accept()


class _LedgerDialog(QDialog):
    """Read-only stock movement ledger for one product."""

    def __init__(self, parent, product_name: str, moves: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(f"Stock Ledger — {product_name}")
        self.setModal(True)
        self.setMinimumSize(620, 420)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(moves), 4)
        table.setHorizontalHeaderLabels(["Date", "Type", "Qty Change", "Note"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for r, m in enumerate(moves):
            table.setItem(r, 0, _cell(m["date"]))
            table.setItem(r, 1, _cell(m["type"]))
            change = _cell(m["qty"])
            table.setItem(r, 2, change)
            table.setItem(r, 3, _cell(m["note"]))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class InventoryScreen(BaseScreen):
    nav_title = "Inventory & Stock"
    nav_permission = "products"
    nav_order = 50

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Inventory & Stock")
        set_class(title, "h1")
        layout.addWidget(title)

        self.valuation_label = QLabel()
        set_class(self.valuation_label, "h2")
        layout.addWidget(self.valuation_label)

        toolbar = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search products (name / SKU / barcode)...")
        self.search_box.returnPressed.connect(self.refresh)
        self.low_only = QCheckBox("Low stock only")
        self.low_only.toggled.connect(self.refresh)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.search_box, 1)
        toolbar.addWidget(self.low_only)
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Product", "SKU", "Category", "Stock Level", "Min Stock",
             "Cost", "Stock Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.adjust_btn = QPushButton("Adjust Stock")
        self.adjust_btn.clicked.connect(self._adjust_stock)
        self.opening_btn = QPushButton("Set Opening Stock")
        self.opening_btn.clicked.connect(self._set_opening)
        self.waste_btn = QPushButton("Record Waste")
        self.waste_btn.clicked.connect(self._record_waste)
        self.ledger_btn = QPushButton("View Ledger")
        self.ledger_btn.clicked.connect(self._view_ledger)
        for b in (self.adjust_btn, self.opening_btn, self.waste_btn, self.ledger_btn):
            self.gate(b, "stock_adjust")
            actions.addWidget(b)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._rows: list[dict] = []

    def on_show(self) -> None:
        self.refresh()

    # -- data ------------------------------------------------------------------
    def refresh(self) -> None:
        query = self.search_box.text().strip()
        low_only = self.low_only.isChecked()
        rows: list[dict] = []
        total = Decimal("0")

        def load():
            with self.db() as s:
                svc = self.svc(s)
                products = svc.catalog.search(query)
                out = []
                for p in products:
                    level = svc.inventory.stock_level(p.id)
                    cat = p.category.name if p.category else ""
                    out.append({
                        "id": p.id, "name": p.name, "sku": p.sku,
                        "category": cat, "level": level,
                        "min": d(p.min_stock or 0), "cost": d(p.cost_price or 0),
                    })
                return out, svc.inventory.valuation()["total"]

        data = self.safe(load)
        if data is None:
            return
        rows, total = data
        if low_only:
            rows = [r for r in rows if r["level"] <= r["min"]]
        self._rows = rows
        self.valuation_label.setText(f"Total stock value: {fmt(total)}")

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            value = q(row["level"] * row["cost"])
            self.table.setItem(r, 0, _cell(row["name"]))
            self.table.setItem(r, 1, _cell(row["sku"]))
            self.table.setItem(r, 2, _cell(row["category"]))
            self.table.setItem(r, 3, _cell(str(row["level"])))
            self.table.setItem(r, 4, _cell(str(row["min"])))
            self.table.setItem(r, 5, _cell(fmt(row["cost"])))
            self.table.setItem(r, 6, _cell(fmt(value)))
        self.table.resizeColumnsToContents()

    # -- selection --------------------------------------------------------------
    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            self.warn("Select a product row first.")
            return None
        return self._rows[row]

    # -- actions -----------------------------------------------------------------
    def _adjust_stock(self) -> None:
        row = self._selected()
        if not row:
            return
        dlg = _StockDialog(self, "Adjust Stock", row["name"],
                           allow_negative=True)
        if dlg.exec() and dlg.result:
            qty_change, note = dlg.result
            if qty_change == 0:
                self.warn("Quantity change is zero — nothing to adjust.")
                return

            def do():
                with self.db() as s:
                    svc = self.svc(s)
                    svc.inventory.adjust(row["id"], qty_change,
                                         self.ctx.actor(s), note=note)
            if self.safe(do) is not None:
                self.info(f"Stock adjusted by {qty_change} for {row['name']}.")
                self.refresh()

    def _set_opening(self) -> None:
        row = self._selected()
        if not row:
            return
        dlg = _StockDialog(self, "Set Opening Stock", row["name"],
                           allow_negative=False, default_qty=float(row["level"]))
        if dlg.exec() and dlg.result:
            qty, _note = dlg.result

            def do():
                with self.db() as s:
                    svc = self.svc(s)
                    svc.inventory.set_opening_stock(row["id"], qty,
                                                   self.ctx.actor(s))
            if self.safe(do) is not None:
                self.info(f"Opening stock set to {qty} for {row['name']}.")
                self.refresh()

    def _record_waste(self) -> None:
        row = self._selected()
        if not row:
            return
        dlg = _StockDialog(self, "Record Waste", row["name"],
                           allow_negative=False)
        if dlg.exec() and dlg.result:
            qty, note = dlg.result
            if qty <= 0:
                self.warn("Waste quantity must be positive.")
                return

            def do():
                with self.db() as s:
                    svc = self.svc(s)
                    svc.inventory.record_waste(row["id"], qty,
                                               self.ctx.actor(s), note=note)
            if self.safe(do) is not None:
                self.info(f"Waste of {qty} recorded for {row['name']}.")
                self.refresh()

    def _view_ledger(self) -> None:
        row = self._selected()
        if not row:
            return

        def load():
            with self.db() as s:
                svc = self.svc(s)
                moves = svc.inventory.ledger(row["id"])
                return [{
                    "date": m.created_at.strftime("%Y-%m-%d %H:%M")
                            if m.created_at else "",
                    "type": m.move_type or "",
                    "qty": str(q(d(m.qty_change or 0))),
                    "note": m.note or "",
                } for m in moves]

        moves = self.safe(load)
        if moves is None:
            return
        _LedgerDialog(self, row["name"], moves).exec()
