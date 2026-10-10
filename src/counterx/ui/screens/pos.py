"""POS screen: "New Sale". Product cards, cart, totals, hold/resume, checkout."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from counterx.services import Cart, CartLine
from counterx.utils.money import d, fmt, q

from ..base import BaseScreen, get_setting
from ..dialogs import CheckoutDialog, TextPreviewDialog
from ..theme import set_class

SALE_TYPES = ["dine_in", "takeaway", "delivery", "online"]


def _fmt_qty(qty) -> str:
    v = d(qty)
    if v == v.to_integral_value():
        return str(int(v))
    return str(v.normalize())


class HeldSalesDialog(QDialog):
    """Pick one held sale to resume. Sets .chosen_id (sale id) or None."""

    def __init__(self, parent, rows: list[dict]):
        super().__init__(parent)
        self.chosen_id: int | None = None
        self._rows = rows
        self.setWindowTitle("Resume Held Sale")
        self.setModal(True)
        self.setMinimumSize(520, 360)

        layout = QVBoxLayout(self)
        title = QLabel("Held sales")
        set_class(title, "h2")
        layout.addWidget(title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Token", "Held at", "Items", "Total"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._accept_current)
        layout.addWidget(self.table)

        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            cells = [r["token_no"], r["held_at"], str(r["items"]), fmt(r["total"])]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, r["id"])
                self.table.setItem(row, c, item)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._accept_current)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_current(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.chosen_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.accept()


class POSScreen(BaseScreen):
    nav_title = "New Sale"
    nav_permission = "sell"
    nav_order = 20

    def __init__(self, ctx, parent=None):
        self._lines: list[CartLine] = []      # plain dataclasses; no ORM objects
        self._products: dict[int, dict] = {}  # product_id -> plain info (for tax rate)
        self.last_sale_id: int | None = None
        super().__init__(ctx, parent)

    # ------------------------------------------------------------------ UI ---
    def build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---------------- left: products ----------------
        left = QVBoxLayout()
        left.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search or scan barcode… (Enter)")
        self.search_edit.returnPressed.connect(self._on_search_enter)
        self.search_edit.textChanged.connect(self._reload_cards)
        left.addWidget(self.search_edit)

        mid = QHBoxLayout()
        mid.setSpacing(8)

        self.cat_list = QListWidget()
        self.cat_list.setMaximumWidth(150)
        self.cat_list.currentRowChanged.connect(lambda _r: self._reload_cards())
        mid.addWidget(self.cat_list)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.cards_widget = QWidget()
        self.cards_grid = QGridLayout(self.cards_widget)
        self.cards_grid.setSpacing(8)
        scroll.setWidget(self.cards_widget)
        mid.addWidget(scroll, 1)
        left.addLayout(mid, 1)

        left_widget = QWidget()
        left_widget.setLayout(left)
        root.addWidget(left_widget, 3)

        # ---------------- right: cart ----------------
        right = QVBoxLayout()
        right.setSpacing(8)

        self.shift_banner = QLabel("No shift open — sale will not be linked to a shift.")
        set_class(self.shift_banner, "muted")
        self.shift_banner.setWordWrap(True)
        self.shift_banner.setVisible(False)
        right.addWidget(self.shift_banner)

        cart_title = QLabel("Cart")
        set_class(cart_title, "h2")
        right.addWidget(cart_title)

        self.cart_table = QTableWidget(0, 4)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Qty", "Price", "Total"])
        self.cart_table.horizontalHeader().setStretchLastSection(True)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        right.addWidget(self.cart_table, 1)

        row_btns = QHBoxLayout()
        self.btn_qty_plus = QPushButton("+ Qty")
        self.btn_qty_plus.clicked.connect(lambda: self._bump_qty(1))
        self.btn_qty_minus = QPushButton("− Qty")
        self.btn_qty_minus.clicked.connect(lambda: self._bump_qty(-1))
        self.btn_remove = QPushButton("Remove")
        self.btn_remove.clicked.connect(self._remove_line)
        self.btn_item_discount = QPushButton("Item Discount")
        self.btn_item_discount.clicked.connect(self._item_discount)
        self.gate(self.btn_item_discount, "discount")
        self.btn_edit_price = QPushButton("Edit Price")
        self.btn_edit_price.clicked.connect(self._edit_price)
        self.gate(self.btn_edit_price, "price_change")
        for b in (self.btn_qty_plus, self.btn_qty_minus, self.btn_remove,
                  self.btn_item_discount, self.btn_edit_price):
            row_btns.addWidget(b)
        right.addLayout(row_btns)

        # totals
        self.tot_labels: dict[str, QLabel] = {}
        totals_grid = QGridLayout()
        totals_grid.setSpacing(4)
        for i, key in enumerate(("subtotal", "discount_total", "tax_total",
                                 "service_charge", "delivery_charge")):
            name = key.replace("_", " ").title()
            lab = QLabel(f"{name}:")
            val = QLabel(fmt(0))
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.tot_labels[key] = val
            totals_grid.addWidget(lab, i, 0)
            totals_grid.addWidget(val, i, 1)
        grand_lab = QLabel("Grand Total:")
        set_class(grand_lab, "h2")
        self.grand_label = QLabel(fmt(0))
        set_class(self.grand_label, "h1")
        self.grand_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        totals_grid.addWidget(grand_lab, 5, 0)
        totals_grid.addWidget(self.grand_label, 5, 1)
        right.addLayout(totals_grid)

        # order options
        opts = QFormLayout()
        self.type_combo = QComboBox()
        for t in SALE_TYPES:
            self.type_combo.addItem(t.replace("_", " ").title(), t)
        self.type_combo.setCurrentIndex(1)  # takeaway
        opts.addRow("Sale type:", self.type_combo)

        self.table_edit = QLineEdit()
        self.table_edit.setPlaceholderText("Table no.")
        opts.addRow("Table:", self.table_edit)
        self.waiter_edit = QLineEdit()
        self.waiter_edit.setPlaceholderText("Waiter name")
        opts.addRow("Waiter:", self.waiter_edit)

        self.customer_combo = QComboBox()
        opts.addRow("Customer:", self.customer_combo)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Notes (optional)")
        opts.addRow("Notes:", self.notes_edit)

        self.service_spin = QDoubleSpinBox()
        self.service_spin.setRange(0, 10_000_000)
        self.service_spin.setDecimals(2)
        self.service_spin.valueChanged.connect(self._refresh_totals)
        opts.addRow("Service charge:", self.service_spin)

        self.delivery_spin = QDoubleSpinBox()
        self.delivery_spin.setRange(0, 10_000_000)
        self.delivery_spin.setDecimals(2)
        self.delivery_spin.valueChanged.connect(self._refresh_totals)
        opts.addRow("Delivery charge:", self.delivery_spin)
        right.addLayout(opts)

        # action buttons
        actions = QGridLayout()
        actions.setSpacing(8)
        self.btn_checkout = QPushButton("Checkout")
        set_class(self.btn_checkout, "primary")
        self.btn_checkout.setMinimumHeight(44)
        self.btn_checkout.clicked.connect(self._checkout)
        self.btn_hold = QPushButton("Hold")
        self.btn_hold.clicked.connect(self._hold)
        self.btn_resume = QPushButton("Resume")
        self.btn_resume.clicked.connect(self._resume)
        self.btn_kot = QPushButton("Print KOT")
        self.btn_kot.clicked.connect(self._print_kot)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_cart)
        actions.addWidget(self.btn_checkout, 0, 0, 1, 2)
        actions.addWidget(self.btn_hold, 1, 0)
        actions.addWidget(self.btn_resume, 1, 1)
        actions.addWidget(self.btn_kot, 2, 0)
        actions.addWidget(self.btn_clear, 2, 1)
        right.addLayout(actions)

        right_widget = QWidget()
        right_widget.setLayout(right)
        root.addWidget(right_widget, 2)

    # -------------------------------------------------------------- loading ---
    def on_show(self) -> None:
        self._load_categories()
        self._load_customers()
        self._reload_cards()
        self._update_shift_banner()
        self._update_mode_visibility()
        self._refresh_cart()

    def _load_categories(self) -> None:
        keep = self.cat_list.currentRow()
        self.cat_list.clear()
        with self.db() as s:
            cats = [(c.id, c.name) for c in self.svc(s).catalog.list_categories()]
        all_item = QListWidgetItem("All")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.cat_list.addItem(all_item)
        for cid, name in cats:
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, cid)
            self.cat_list.addItem(it)
        self.cat_list.setCurrentRow(max(0, min(keep, self.cat_list.count() - 1)))

    def _load_customers(self) -> None:
        self.customer_combo.clear()
        self.customer_combo.addItem("— Walk-in —", None)
        with self.db() as s:
            for c in self.svc(s).directory.list_customers():
                self.customer_combo.addItem(c.name, c.id)

    def _current_category(self):
        item = self.cat_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _reload_cards(self) -> None:
        cat_id = self._current_category()
        query = self.search_edit.text().strip()
        with self.db() as s:
            svc = self.svc(s)
            products = svc.catalog.search(query)
            self._products = {}
            rows = []
            for p in products:
                if cat_id is not None and p.category_id != cat_id:
                    continue
                tax = svc.catalog.tax_rate_of(p)
                self._products[p.id] = {
                    "id": p.id, "name": p.name, "name_ur": p.name_ur or "",
                    "price": d(p.sell_price), "tax": tax,
                }
                rows.append(self._products[p.id])

        # clear grid
        while self.cards_grid.count():
            child = self.cards_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        cols = 3
        for i, info in enumerate(rows):
            label_lines = [info["name"]]
            if info["name_ur"]:
                label_lines.append(info["name_ur"])
            label_lines.append(fmt(info["price"]))
            btn = QPushButton("\n".join(label_lines))
            btn.setMinimumSize(130, 64)
            btn.clicked.connect(lambda _=False, pid=info["id"]: self._add_product(pid))
            self.cards_grid.addWidget(btn, i // cols, i % cols)

    def _on_search_enter(self) -> None:
        text = self.search_edit.text().strip()
        if not text:
            return
        p = None
        with self.db() as s:
            p = self.svc(s).catalog.find_by_barcode(text)
            if p is not None:
                pid, name, price = p.id, p.name, d(p.sell_price)
                tax = self.svc(s).catalog.tax_rate_of(p)
                self._products[pid] = {"id": pid, "name": name,
                                       "name_ur": p.name_ur or "",
                                       "price": price, "tax": tax}
        if p is not None:
            self._add_product(pid)
            self.search_edit.clear()

    # ----------------------------------------------------------------- cart ---
    def _add_product(self, product_id: int) -> None:
        info = self._products.get(product_id)
        if info is None:
            return
        for line in self._lines:
            if line.product_id == product_id and line.variant_id is None:
                line.qty = q(line.qty + 1)
                self._refresh_cart()
                return
        self._lines.append(CartLine(
            product_id=product_id, variant_id=None, name=info["name"],
            qty=Decimal("1"), unit_price=info["price"],
            item_discount=Decimal("0"), tax_rate=info["tax"], modifiers=[]))
        self._refresh_cart()

    def _selected_line(self) -> CartLine | None:
        row = self.cart_table.currentRow()
        if 0 <= row < len(self._lines):
            return self._lines[row]
        return None

    def _bump_qty(self, delta: int) -> None:
        line = self._selected_line()
        if line is None:
            return
        line.qty = q(line.qty + delta)
        if line.qty <= 0:
            self._lines.remove(line)
        self._refresh_cart()

    def _remove_line(self) -> None:
        line = self._selected_line()
        if line is None:
            return
        self._lines.remove(line)
        self._refresh_cart()

    def _item_discount(self) -> None:
        line = self._selected_line()
        if line is None:
            return
        current = float(line.item_discount)
        value, ok = QInputDialog.getDouble(
            self, "Item Discount", f"Discount on '{line.name}' (Rs):",
            current, 0, 10_000_000, 2)
        if ok:
            line.item_discount = q(value)
            self._refresh_cart()

    def _edit_price(self) -> None:
        line = self._selected_line()
        if line is None:
            return
        value, ok = QInputDialog.getDouble(
            self, "Edit Price", f"New unit price for '{line.name}' (Rs):",
            float(line.unit_price), 0, 10_000_000, 2)
        if ok:
            line.unit_price = q(value)
            self._refresh_cart()

    def _build_cart(self) -> Cart:
        return Cart(
            lines=list(self._lines),
            sale_type=self.type_combo.currentData() or "takeaway",
            table_no=self.table_edit.text().strip(),
            waiter=self.waiter_edit.text().strip(),
            customer_id=self.customer_combo.currentData(),
            notes=self.notes_edit.text().strip(),
            service_charge=q(self.service_spin.value()),
            delivery_charge=q(self.delivery_spin.value()),
        )

    def _cart_totals(self) -> dict:
        cart = self._build_cart()
        with self.db() as s:
            return self.svc(s).sales.cart_totals(cart)

    def _refresh_cart(self) -> None:
        self.cart_table.setRowCount(0)
        for line in self._lines:
            row = self.cart_table.rowCount()
            self.cart_table.insertRow(row)
            line_total = q(line.qty * line.unit_price - line.item_discount)
            cells = [line.name, _fmt_qty(line.qty), fmt(line.unit_price),
                     fmt(line_total)]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                self.cart_table.setItem(row, c, item)
        self._refresh_totals()

    def _refresh_totals(self) -> None:
        try:
            totals = self._cart_totals()
        except Exception:  # keep labels unchanged on transient errors
            return
        for key, lbl in self.tot_labels.items():
            lbl.setText(fmt(totals[key]))
        self.grand_label.setText(fmt(totals["grand_total"]))

    def _clear_cart(self) -> None:
        self._lines = []
        self.service_spin.setValue(0)
        self.delivery_spin.setValue(0)
        self.notes_edit.clear()
        self._refresh_cart()

    # ------------------------------------------------------------- checkout ---
    def _checkout(self) -> None:
        if not self._lines:
            self.warn("Cart is empty.")
            return
        cart = self._build_cart()
        totals = self.safe(lambda: self._cart_totals())
        if totals is None:
            return
        dlg = CheckoutDialog(self, totals["grand_total"])
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.payments:
            return
        payments = dlg.payments

        def _do():
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                shift = svc.shifts.current_shift()
                sale = svc.sales.checkout(
                    cart, payments, actor, shift.id if shift else None)
                sid, inv_no = sale.id, sale.invoice_no
                receipt = svc.printing.receipt(sale.id)
                printer = get_setting(s, "receipt_printer", "")
            self.last_sale_id = sid
            self._clear_cart()
            TextPreviewDialog(self, f"Receipt #{inv_no}", receipt, printer).exec()

        self.safe(_do)
        self._update_shift_banner()

    # ------------------------------------------------------------ hold/resume -
    def _hold(self) -> None:
        if not self._lines:
            self.warn("Cart is empty.")
            return
        cart = self._build_cart()

        def _do():
            with self.db() as s:
                sale = self.svc(s).sales.hold_sale(cart, self.ctx.actor(s))
                return sale.token_no, sale.grand_total

        res = self.safe(_do)
        if res:
            token, total = res
            self.info(f"Sale held.\nToken: {token}\nTotal: {fmt(total)}")
            self._clear_cart()

    def _resume(self) -> None:
        with self.db() as s:
            held = self.svc(s).sales.held_sales()
            rows = [{"id": x.id, "token_no": x.token_no,
                     "held_at": x.created_at.strftime("%Y-%m-%d %H:%M"),
                     "items": len(x.items), "total": d(x.grand_total)}
                    for x in held]
        if not rows:
            self.info("No held sales.")
            return
        dlg = HeldSalesDialog(self, rows)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.chosen_id is None:
            return
        sale_id = dlg.chosen_id

        def _do():
            with self.db() as s:
                svc = self.svc(s).sales
                sale = svc.get_sale(sale_id)
                if sale is None or sale.status != "held":
                    raise ValueError("Held sale not found or already processed.")
                lines = [CartLine(
                    product_id=i.product_id, variant_id=i.variant_id,
                    name=i.name_snapshot, qty=d(i.qty),
                    unit_price=d(i.unit_price),
                    item_discount=d(i.item_discount or 0),
                    tax_rate=Decimal("0"), modifiers=[])
                    for i in sale.items]
                opts = {"sale_type": sale.sale_type, "table_no": sale.table_no or "",
                        "waiter": sale.waiter or "", "customer_id": sale.customer_id,
                        "notes": sale.notes or ""}
                # Consume the held row now: it can never be resumed twice.
                svc.release_hold(sale_id, self.ctx.actor(s))
                return lines, opts

        res = self.safe(_do)
        if res is None:
            return
        lines, opts = res
        self._lines = lines
        idx = self.type_combo.findData(opts["sale_type"])
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.table_edit.setText(opts["table_no"])
        self.waiter_edit.setText(opts["waiter"])
        cidx = self.customer_combo.findData(opts["customer_id"])
        self.customer_combo.setCurrentIndex(max(0, cidx))
        self.notes_edit.setText(opts["notes"])
        self._refresh_cart()
        self.info("Held sale resumed into the cart.")

    # ----------------------------------------------------------------- misc ---
    def _print_kot(self) -> None:
        if self.last_sale_id is None:
            self.warn("No sale yet. Complete a sale first, then print its KOT.")
            return

        def _do():
            with self.db() as s:
                return self.svc(s).printing.kot(self.last_sale_id)

        text = self.safe(_do)
        if text:
            TextPreviewDialog(self, "Kitchen Order Ticket", text).exec()

    def _update_shift_banner(self) -> None:
        with self.db() as s:
            shift = self.svc(s).shifts.current_shift()
        self.shift_banner.setVisible(shift is None)

    def _update_mode_visibility(self) -> None:
        with self.db() as s:
            mode = get_setting(s, "business_mode", "restaurant")
        restaurant = (mode == "restaurant")
        self.table_edit.setVisible(restaurant)
        self.waiter_edit.setVisible(restaurant)
