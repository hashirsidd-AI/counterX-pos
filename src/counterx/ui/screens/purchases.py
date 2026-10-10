"""Purchases screen: receive supplier purchases + purchase history."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ... import models
from ...utils.money import d, fmt, q
from ..base import BaseScreen
from ..theme import set_class


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _spin(decimals: int = 3, max_value: float = 1_000_000.0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, max_value)
    spin.setDecimals(decimals)
    spin.setMinimumWidth(120)
    return spin


class _PurchaseItemsDialog(QDialog):
    """Line items of one purchase (read-only)."""

    def __init__(self, parent, title: str, lines: list[dict]):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(560, 380)
        layout = QVBoxLayout(self)
        table = QTableWidget(len(lines), 4)
        table.setHorizontalHeaderLabels(
            ["Product", "Qty", "Unit Cost", "Line Total"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for r, line in enumerate(lines):
            table.setItem(r, 0, _cell(line["product"]))
            table.setItem(r, 1, _cell(line["qty"]))
            table.setItem(r, 2, _cell(fmt(line["unit_cost"])))
            table.setItem(r, 3, _cell(fmt(line["line_total"])))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class _LineRow(QWidget):
    """One purchase line: product picker + qty + unit cost + remove."""

    def __init__(self, products: list[tuple[int, str]], on_remove, parent=None):
        super().__init__(parent)
        self.on_remove = on_remove
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.product = QComboBox()
        self.product.addItem("— Select product —", None)
        for pid, label in products:
            self.product.addItem(label, pid)
        self.product.setMinimumWidth(260)
        self.qty = _spin(decimals=3)
        self.qty.setValue(1.0)
        self.unit_cost = _spin(decimals=2)
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda _=False: self.on_remove(self))
        layout.addWidget(self.product, 1)
        layout.addWidget(QLabel("Qty:"))
        layout.addWidget(self.qty)
        layout.addWidget(QLabel("Unit cost:"))
        layout.addWidget(self.unit_cost)
        layout.addWidget(remove)

    def as_item(self) -> dict | None:
        pid = self.product.currentData()
        if pid is None:
            return None
        qty = q(d(self.qty.value()))
        cost = q(d(self.unit_cost.value()))
        if qty <= 0:
            raise ValueError("Line quantity must be positive.")
        return {"product_id": pid, "qty": qty, "unit_cost": cost}


class PurchasesScreen(BaseScreen):
    nav_title = "Purchases"
    nav_permission = "purchases"
    nav_order = 90

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Purchases")
        set_class(title, "h1")
        layout.addWidget(title)

        # -- new purchase ------------------------------------------------------
        group = QGroupBox("New Purchase")
        g_layout = QVBoxLayout(group)

        head = QHBoxLayout()
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(240)
        self.invoice_ref = QLineEdit()
        self.invoice_ref.setPlaceholderText("Invoice ref (optional)")
        head.addWidget(QLabel("Supplier:"))
        head.addWidget(self.supplier_combo)
        head.addWidget(QLabel("Invoice ref:"))
        head.addWidget(self.invoice_ref, 1)
        g_layout.addLayout(head)

        self.lines_box = QVBoxLayout()
        g_layout.addLayout(self.lines_box)

        add_line_btn = QPushButton("Add line")
        add_line_btn.clicked.connect(self._add_line_row)
        g_layout.addWidget(add_line_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.receive_btn = QPushButton("Receive Purchase")
        set_class(self.receive_btn, "primary")
        self.receive_btn.clicked.connect(self._receive_purchase)
        self.gate(self.receive_btn, "purchases")
        g_layout.addWidget(self.receive_btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addWidget(group)

        # -- history -----------------------------------------------------------
        hist_title = QLabel("Purchase History")
        set_class(hist_title, "h2")
        layout.addWidget(hist_title)

        self.history = QTableWidget(0, 6)
        self.history.setHorizontalHeaderLabels(
            ["ID", "Date", "Supplier", "Invoice Ref", "Total", "By"])
        self.history.horizontalHeader().setStretchLastSection(True)
        self.history.setAlternatingRowColors(True)
        self.history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.history.itemDoubleClicked.connect(self._open_purchase_detail)
        layout.addWidget(self.history, 1)

        self._line_rows: list[_LineRow] = []
        self._history_rows: list[dict] = []

    def on_show(self) -> None:
        self.refresh()

    # -- data ------------------------------------------------------------------
    def refresh(self) -> None:
        def load():
            with self.db() as s:
                svc = self.svc(s)
                suppliers = [(sp.id, sp.name)
                             for sp in svc.directory.list_suppliers()]
                products = [(p.id, f"{p.name} ({p.sku})")
                            for p in svc.catalog.search("")]
                purchases = (s.query(models.Purchase)
                             .order_by(models.Purchase.created_at.desc(),
                                       models.Purchase.id.desc())
                             .limit(200).all())
                rows = []
                for pu in purchases:
                    sup_name = "Walk-in"
                    if pu.supplier_id:
                        sup = s.get(models.Supplier, pu.supplier_id)
                        if sup:
                            sup_name = sup.name
                    user = s.get(models.User, pu.user_id)
                    rows.append({
                        "id": pu.id,
                        "date": pu.created_at.strftime("%Y-%m-%d %H:%M")
                                if pu.created_at else "",
                        "supplier": sup_name,
                        "invoice_ref": pu.invoice_ref or "",
                        "total": d(pu.total or 0),
                        "by": user.username if user else "",
                    })
                return suppliers, products, rows

        data = self.safe(load)
        if data is None:
            return
        suppliers, products, rows = data

        self.supplier_combo.blockSignals(True)
        self.supplier_combo.clear()
        self.supplier_combo.addItem("Walk-in", None)
        for sid, name in suppliers:
            self.supplier_combo.addItem(name, sid)
        self.supplier_combo.blockSignals(False)

        self._products = products
        self._reset_line_rows()

        self._history_rows = rows
        self.history.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.history.setItem(r, 0, _cell(str(row["id"])))
            self.history.setItem(r, 1, _cell(row["date"]))
            self.history.setItem(r, 2, _cell(row["supplier"]))
            self.history.setItem(r, 3, _cell(row["invoice_ref"]))
            self.history.setItem(r, 4, _cell(fmt(row["total"])))
            self.history.setItem(r, 5, _cell(row["by"]))
        self.history.resizeColumnsToContents()

    # -- line rows ---------------------------------------------------------------
    def _reset_line_rows(self) -> None:
        for row in self._line_rows:
            self.lines_box.removeWidget(row)
            row.deleteLater()
        self._line_rows = []
        self._add_line_row()

    def _add_line_row(self) -> None:
        row = _LineRow(getattr(self, "_products", []),
                       on_remove=self._remove_line_row, parent=self)
        self._line_rows.append(row)
        self.lines_box.addWidget(row)

    def _remove_line_row(self, row: _LineRow) -> None:
        if len(self._line_rows) <= 1:
            return
        self._line_rows.remove(row)
        self.lines_box.removeWidget(row)
        row.deleteLater()

    # -- receive ------------------------------------------------------------------
    def _receive_purchase(self) -> None:
        try:
            items = []
            for row in self._line_rows:
                item = row.as_item()
                if item:
                    items.append(item)
        except ValueError as e:
            self.warn(str(e))
            return
        if not items:
            self.warn("Add at least one line with a product selected.")
            return
        supplier_id = self.supplier_combo.currentData()
        invoice_ref = self.invoice_ref.text().strip()

        def do():
            with self.db() as s:
                svc = self.svc(s)
                purchase = svc.inventory.receive_purchase(
                    supplier_id, items, self.ctx.actor(s),
                    invoice_ref=invoice_ref)
                return purchase.id, d(purchase.total or 0)

        result = self.safe(do)
        if result is None:
            return
        pid, total = result
        self.info(f"Purchase #{pid} received. Total: {fmt(total)}")
        self.invoice_ref.clear()
        self.refresh()

    # -- history detail ------------------------------------------------------------
    def _open_purchase_detail(self, _item) -> None:
        row = self.history.currentRow()
        if row < 0 or row >= len(self._history_rows):
            return
        purchase_id = self._history_rows[row]["id"]

        def load():
            with self.db() as s:
                items = (s.query(models.PurchaseItem)
                         .filter_by(purchase_id=purchase_id)
                         .order_by(models.PurchaseItem.id).all())
                return [{
                    "product": (s.get(models.Product, it.product_id).name
                                if s.get(models.Product, it.product_id) else
                                f"Product #{it.product_id}"),
                    "qty": str(q(d(it.qty or 0))),
                    "unit_cost": d(it.unit_cost or 0),
                    "line_total": d(it.line_total or 0),
                } for it in items]

        lines = self.safe(load)
        if lines is None:
            return
        _PurchaseItemsDialog(self, f"Purchase #{purchase_id} — Items",
                             lines).exec()
