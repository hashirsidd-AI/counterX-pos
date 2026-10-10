"""Orders screen: search order history and manage sales (view/refund/void/print)."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from counterx import models
from counterx.utils.money import d, fmt

from ..base import BaseScreen, get_setting
from ..dialogs import TextPreviewDialog
from ..theme import set_class

STATUSES = [("all", "All"), ("completed", "Completed"), ("held", "Held"),
            ("voided", "Voided"), ("refunded", "Refunded")]


class SaleDetailDialog(QDialog):
    """Sale detail with items, payments, totals and management actions.

    Expects fully plain data (no ORM objects). Signals the parent to refresh
    via .refresh_requested after a void/refund.
    """

    def __init__(self, parent, data: dict):
        super().__init__(parent)
        self.data = data
        self.refresh_requested = False
        self.setWindowTitle(f"Sale #{data['invoice_no']} — {data['token_no']}")
        self.setModal(True)
        self.setMinimumSize(560, 560)

        layout = QVBoxLayout(self)
        head = QLabel(f"Invoice #{data['invoice_no']}  •  Token {data['token_no']}  •  "
                      f"{data['time']}  •  {data['status'].title()}")
        set_class(head, "h2")
        head.setWordWrap(True)
        layout.addWidget(head)
        meta = QLabel(f"Type: {data['sale_type']}  •  Cashier: {data['cashier']}  •  "
                      f"Table: {data['table_no'] or '—'}  •  Waiter: {data['waiter'] or '—'}")
        set_class(meta, "muted")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        items_title = QLabel("Items")
        set_class(items_title, "h2")
        layout.addWidget(items_title)
        self.items_table = QTableWidget(0, 4)
        self.items_table.setHorizontalHeaderLabels(["Item", "Qty", "Price", "Total"])
        self.items_table.horizontalHeader().setStretchLastSection(True)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for it in data["items"]:
            row = self.items_table.rowCount()
            self.items_table.insertRow(row)
            cells = [it["name"], str(it["qty"]), fmt(it["price"]), fmt(it["total"])]
            for c, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if c > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                self.items_table.setItem(row, c, cell)
        layout.addWidget(self.items_table, 1)

        pay_title = QLabel("Payments")
        set_class(pay_title, "h2")
        layout.addWidget(pay_title)
        self.pay_table = QTableWidget(0, 3)
        self.pay_table.setHorizontalHeaderLabels(["Method", "Amount", "Received"])
        self.pay_table.horizontalHeader().setStretchLastSection(True)
        self.pay_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for p in data["payments"]:
            row = self.pay_table.rowCount()
            self.pay_table.insertRow(row)
            cells = [p["method"], fmt(p["amount"]), fmt(p["received"])]
            for c, text in enumerate(cells):
                self.pay_table.setItem(row, c, QTableWidgetItem(text))
        layout.addWidget(self.pay_table)

        form = QFormLayout()
        for key, label in (("subtotal", "Subtotal"), ("discount_total", "Discount"),
                           ("tax_total", "Tax"), ("service_charge", "Service charge"),
                           ("delivery_charge", "Delivery charge")):
            val = QLabel(fmt(data[key]))
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            form.addRow(f"{label}:", val)
        grand = QLabel(fmt(data["grand_total"]))
        set_class(grand, "h1")
        grand.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Grand total:", grand)
        layout.addLayout(form)

        row = QHBoxLayout()
        self.btn_receipt = QPushButton("Print Receipt")
        self.btn_receipt.clicked.connect(
            lambda: parent.preview_text(f"Receipt #{data['invoice_no']}",
                                        parent.sale_text(data["id"], "receipt")))
        self.btn_kot = QPushButton("Print KOT")
        self.btn_kot.clicked.connect(
            lambda: parent.preview_text("Kitchen Order Ticket",
                                        parent.sale_text(data["id"], "kot")))
        self.btn_refund = QPushButton("Refund")
        set_class(self.btn_refund, "danger")
        self.btn_refund.clicked.connect(self._refund)
        parent.gate(self.btn_refund, "refund")
        self.btn_void = QPushButton("Void")
        set_class(self.btn_void, "danger")
        self.btn_void.clicked.connect(self._void)
        parent.gate(self.btn_void, "void")
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        for b in (self.btn_receipt, self.btn_kot, self.btn_refund,
                  self.btn_void, close_btn):
            row.addWidget(b)
        layout.addLayout(row)

        self._parent = parent
        self._sync_action_state()

    def _sync_action_state(self) -> None:
        active = self.data["status"] == "completed"
        self.btn_refund.setEnabled(active)
        self.btn_void.setEnabled(active)

    def _refund(self) -> None:
        value, ok = QInputDialog.getDouble(
            self, "Refund", "Refund amount (Rs):",
            float(self.data["grand_total"]), 0,
            float(self.data["grand_total"]), 2)
        if not ok:
            return
        reason, rok = QInputDialog.getText(self, "Refund", "Reason (optional):")
        if not rok:
            return

        def _do():
            with self._parent.db() as s:
                svc = self._parent.svc(s)
                svc.sales.refund(self.data["id"], d(value),
                                 self._parent.ctx.actor(s), reason.strip())
                sale = svc.sales.get_sale(self.data["id"])
                return sale.status if sale else None

        status = self._parent.safe(_do)
        if status is not None:
            self.data["status"] = status
            self.refresh_requested = True
            self._sync_action_state()
            self._parent.info(f"Refund of {fmt(value)} recorded.")

    def _void(self) -> None:
        if not self._parent.confirm(
                f"Void invoice #{self.data['invoice_no']} ({fmt(self.data['grand_total'])})?\n"
                "This cannot be undone."):
            return
        reason, ok = QInputDialog.getText(self, "Void", "Reason (optional):")
        if not ok:
            return

        def _do():
            with self._parent.db() as s:
                svc = self._parent.svc(s)
                sale = svc.sales.void_sale(self.data["id"],
                                           self._parent.ctx.actor(s), reason.strip())
                return sale.status

        status = self._parent.safe(_do)
        if status is not None:
            self.data["status"] = status
            self.refresh_requested = True
            self._sync_action_state()
            self._parent.info(f"Invoice #{self.data['invoice_no']} voided.")


class OrdersScreen(BaseScreen):
    nav_title = "Orders & History"
    nav_permission = "sell"
    nav_order = 60

    # ------------------------------------------------------------------ UI ---
    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Orders & History")
        set_class(title, "h1")
        root.addWidget(title)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        filters.addWidget(self.date_edit)

        filters.addWidget(QLabel("Token:"))
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Search token…")
        self.token_edit.setMaximumWidth(160)
        filters.addWidget(self.token_edit)

        filters.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        for value, label in STATUSES:
            self.status_combo.addItem(label, value)
        filters.addWidget(self.status_combo)

        self.btn_search = QPushButton("Search")
        set_class(self.btn_search, "primary")
        self.btn_search.clicked.connect(self._search)
        filters.addWidget(self.btn_search)
        filters.addStretch(1)
        root.addLayout(filters)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["Invoice", "Token", "Time", "Type", "Items", "Total", "Status", "Cashier"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_selected)
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_view = QPushButton("View / Manage")
        self.btn_view.clicked.connect(self._open_selected)
        row.addWidget(self.btn_view)
        row.addStretch(1)
        root.addLayout(row)

    def on_show(self) -> None:
        self._search()

    # --------------------------------------------------------------- search ---
    def _search(self) -> None:
        day = self.date_edit.date().toString("yyyy-MM-dd")
        token = self.token_edit.text().strip()
        status = self.status_combo.currentData()

        def _do():
            with self.db() as s:
                qy = s.query(models.Sale).filter(models.Sale.business_day == day)
                if token:
                    qy = qy.filter(models.Sale.token_no.ilike(f"%{token}%"))
                if status != "all":
                    qy = qy.filter(models.Sale.status == status)
                sales = qy.order_by(models.Sale.created_at.desc()).all()
                rows = []
                for sale in sales:
                    cashier = s.get(models.User, sale.user_id)
                    rows.append({
                        "id": sale.id,
                        "invoice_no": sale.invoice_no,
                        "token_no": sale.token_no,
                        "time": sale.created_at.strftime("%H:%M"),
                        "sale_type": (sale.sale_type or "").replace("_", " ").title(),
                        "items": len(sale.items),
                        "total": d(sale.grand_total),
                        "status": sale.status,
                        "cashier": cashier.username if cashier else "",
                    })
                return rows

        rows = self.safe(_do)
        if rows is None:
            return
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = [str(r["invoice_no"]), r["token_no"], r["time"],
                     r["sale_type"], str(r["items"]), fmt(r["total"]),
                     r["status"].title(), r["cashier"]]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r["id"])
                if c in (4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, c, item)

    # --------------------------------------------------------------- detail ---
    def _selected_sale_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _open_selected(self) -> None:
        sale_id = self._selected_sale_id()
        if sale_id is None:
            self.warn("Select a sale first.")
            return
        data = self._load_sale_detail(sale_id)
        if data is None:
            return
        dlg = SaleDetailDialog(self, data)
        dlg.exec()
        if dlg.refresh_requested:
            self._search()

    def _load_sale_detail(self, sale_id: int) -> dict | None:
        def _do():
            with self.db() as s:
                sale = self.svc(s).sales.get_sale(sale_id)
                if sale is None:
                    raise ValueError("Sale not found.")
                cashier = s.get(models.User, sale.user_id)
                return {
                    "id": sale.id,
                    "invoice_no": sale.invoice_no,
                    "token_no": sale.token_no,
                    "time": sale.created_at.strftime("%Y-%m-%d %H:%M"),
                    "sale_type": (sale.sale_type or "").replace("_", " ").title(),
                    "table_no": sale.table_no or "",
                    "waiter": sale.waiter or "",
                    "cashier": cashier.username if cashier else "",
                    "status": sale.status,
                    "items": [{"name": i.name_snapshot, "qty": d(i.qty),
                               "price": d(i.unit_price), "total": d(i.line_total)}
                              for i in sale.items],
                    "payments": [{"method": p.method, "amount": d(p.amount),
                                  "received": d(p.received)} for p in sale.payments],
                    "subtotal": d(sale.subtotal),
                    "discount_total": d(sale.discount_total),
                    "tax_total": d(sale.tax_total),
                    "service_charge": d(sale.service_charge),
                    "delivery_charge": d(sale.delivery_charge),
                    "grand_total": d(sale.grand_total),
                }

        return self.safe(_do)

    def sale_text(self, sale_id: int, kind: str) -> str | None:
        def _do():
            with self.db() as s:
                svc = self.svc(s)
                if kind == "receipt":
                    return svc.printing.receipt(sale_id)
                return svc.printing.kot(sale_id)

        return self.safe(_do)

    def preview_text(self, title: str, text: str | None) -> None:
        if not text:
            return
        printer = ""
        with self.db() as s:
            printer = get_setting(s, "receipt_printer", "")
        TextPreviewDialog(self, title, text, printer).exec()
