"""Products & menu management screen (catalog CRUD, CSV I/O, modifiers)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)
from sqlalchemy import or_

from ... import models
from ...utils.money import d, q
from ..base import BaseScreen
from ..theme import set_class


def _price_spin(decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, 10_000_000.0)
    s.setDecimals(decimals)
    s.setMinimumWidth(180)
    return s


class ProductDialog(QDialog):
    """Add / edit a product. Saves via CatalogService inside ``safe()``."""

    def __init__(self, screen: "ProductsScreen", product_id: int | None = None):
        super().__init__(screen)
        self._screen = screen
        self._product_id = product_id
        self.setWindowTitle("Edit Product" if product_id else "Add Product")
        self.setModal(True)
        self.setMinimumWidth(440)

        form = QFormLayout(self)
        self.sku = QLineEdit()
        self.name = QLineEdit()
        self.name_ur = QLineEdit()
        self.name_ur.setPlaceholderText("اردو نام")
        self.barcode = QLineEdit()
        self.category = QComboBox()
        self.cost_price = _price_spin()
        self.sell_price = _price_spin()
        self.tax = QComboBox()
        self.track_stock = QCheckBox("Track stock for this product")
        self.track_stock.setChecked(True)
        self.min_stock = _price_spin(decimals=3)
        self.description = QTextEdit()
        self.description.setMaximumHeight(70)

        form.addRow("SKU *:", self.sku)
        form.addRow("Name *:", self.name)
        form.addRow("Urdu name:", self.name_ur)
        form.addRow("Barcode:", self.barcode)
        form.addRow("Category:", self.category)
        form.addRow("Cost price:", self.cost_price)
        form.addRow("Sell price:", self.sell_price)
        form.addRow("Tax rate:", self.tax)
        form.addRow("", self.track_stock)
        form.addRow("Min stock:", self.min_stock)
        form.addRow("Description:", self.description)

        # -- fill combos (plain values, inside session) --
        self.category.addItem("No category", None)
        self.tax.addItem("Default tax", None)
        with screen.db() as s:
            svc = screen.svc(s)
            cats = [(c.id, c.name) for c in
                    svc.catalog.list_categories(active_only=False)]
            rates = [(r.id, r.name, r.rate_percent) for r in
                     svc.directory.list_tax_rates()]
        for cid, cname in cats:
            self.category.addItem(cname, cid)
        for rid, rname, pct in rates:
            self.tax.addItem(f"{rname} ({pct}%)", rid)

        if product_id is not None:
            self._load(product_id)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _load(self, product_id: int) -> None:
        with self._screen.db() as s:
            p = s.get(models.Product, product_id)
            if p is None:
                return
            data = dict(sku=p.sku, name=p.name, name_ur=p.name_ur or "",
                        barcode=p.barcode or "", category_id=p.category_id,
                        cost=float(p.cost_price or 0),
                        sell=float(p.sell_price or 0),
                        tax_rate_id=p.tax_rate_id,
                        track=p.track_stock, min_stock=float(p.min_stock or 0),
                        description=p.description or "")
        self.sku.setText(data["sku"])
        self.name.setText(data["name"])
        self.name_ur.setText(data["name_ur"])
        self.barcode.setText(data["barcode"])
        idx = self.category.findData(data["category_id"])
        self.category.setCurrentIndex(max(idx, 0))
        self.cost_price.setValue(data["cost"])
        self.sell_price.setValue(data["sell"])
        idx = self.tax.findData(data["tax_rate_id"])
        self.tax.setCurrentIndex(max(idx, 0))
        self.track_stock.setChecked(data["track"])
        self.min_stock.setValue(data["min_stock"])
        self.description.setPlainText(data["description"])

    def _save(self) -> None:
        payload = dict(
            sku=self.sku.text().strip(),
            name=self.name.text().strip(),
            barcode=self.barcode.text().strip() or None,
            category_id=self.category.currentData(),
            cost_price=q(d(str(self.cost_price.value()))),
            sell_price=q(d(str(self.sell_price.value()))),
            tax_rate_id=self.tax.currentData(),
            track_stock=self.track_stock.isChecked(),
            min_stock=q(d(str(self.min_stock.value()))),
            name_ur=self.name_ur.text().strip(),
            description=self.description.toPlainText().strip(),
        )

        def do() -> bool:
            with self._screen.db() as s:
                svc = self._screen.svc(s)
                actor = self._screen.ctx.actor(s)
                if self._product_id is None:
                    svc.catalog.create_product(actor, **payload)
                else:
                    svc.catalog.update_product(self._product_id, actor, **payload)
            return True

        if self._screen.safe(do):
            self.accept()


class ProductModifiersDialog(QDialog):
    """Tick modifiers to attach to a product (v1: no detach API)."""

    def __init__(self, screen: "ProductsScreen", product_id: int,
                 product_name: str):
        super().__init__(screen)
        self._screen = screen
        self._product_id = product_id
        self.setWindowTitle(f"Modifiers — {product_name}")
        self.setModal(True)
        self.setMinimumSize(380, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Attach modifiers to “{product_name}”:"))
        self._items: list[tuple[int, QListWidgetItem]] = []
        self.list = QListWidget()
        layout.addWidget(self.list)

        with screen.db() as s:
            mods = [(m.id, m.name, m.price) for m in
                    s.query(models.Modifier).order_by(models.Modifier.name).all()]
            attached = {pm.modifier_id for pm in
                        s.query(models.ProductModifier)
                        .filter_by(product_id=product_id).all()}
        for mid, mname, mprice in mods:
            item = QListWidgetItem(f"{mname} (+{screen.money(mprice)})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if mid in attached
                               else Qt.CheckState.Unchecked)
            self.list.addItem(item)
            self._items.append((mid, item))
        if not mods:
            self.list.addItem("(No modifiers defined yet — create them under "
                              "Categories & Modifiers.)")

        note = QLabel("Note: detaching a modifier is not supported in v1 — "
                      "unticking a box will not detach it.")
        note.setWordWrap(True)
        set_class(note, "muted")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        checked = [mid for mid, item in self._items
                   if item.checkState() == Qt.CheckState.Checked]

        def do() -> bool:
            with self._screen.db() as s:
                svc = self._screen.svc(s)
                actor = self._screen.ctx.actor(s)
                for mid in checked:
                    svc.catalog.attach_modifier(self._product_id, mid, actor)
            return True

        if self._screen.safe(do):
            self.accept()


class BulkPriceDialog(QDialog):
    """Apply a percentage price change to a category (or all products)."""

    def __init__(self, screen: "ProductsScreen"):
        super().__init__(screen)
        self._screen = screen
        self.setWindowTitle("Bulk Price Update")
        self.setModal(True)
        self.setMinimumWidth(360)

        form = QFormLayout(self)
        self.category = QComboBox()
        self.category.addItem("All products", None)
        with screen.db() as s:
            cats = [(c.id, c.name) for c in
                    screen.svc(s).catalog.list_categories(active_only=False)]
        for cid, cname in cats:
            self.category.addItem(cname, cid)
        self.percent = QDoubleSpinBox()
        self.percent.setRange(-100, 1000)
        self.percent.setDecimals(2)
        self.percent.setSuffix(" %")
        self.percent.setValue(0)
        form.addRow("Category:", self.category)
        form.addRow("Change:", self.percent)

        note = QLabel("Example: 10 adds 10%, -5 reduces prices by 5%. "
                      "Applies to active products only.")
        note.setWordWrap(True)
        set_class(note, "muted")
        form.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _apply(self) -> None:
        cat_id = self.category.currentData()
        percent = d(str(self.percent.value()))
        if not self._screen.confirm(
                f"Change prices by {self.percent.value()}% for "
                f"{'all products' if cat_id is None else 'this category'}?"):
            return

        def do() -> int:
            with self._screen.db() as s:
                svc = self._screen.svc(s)
                actor = self._screen.ctx.actor(s)
                return svc.catalog.bulk_price_update(cat_id, percent, actor)

        count = self._screen.safe(do)
        if count is not None:
            self._screen.info(f"Updated {count} product(s).")
            self.accept()


class ProductsScreen(BaseScreen):
    nav_title = "Products & Menu"
    nav_permission = "products"
    nav_order = 30

    # -- UI -------------------------------------------------------------------
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Products & Menu")
        set_class(title, "h1")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name, SKU or barcode…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search, 2)

        self.cat_filter = QComboBox()
        self.cat_filter.currentIndexChanged.connect(self.refresh)
        toolbar.addWidget(self.cat_filter, 1)

        self.add_btn = QPushButton("Add")
        set_class(self.add_btn, "primary")
        self.add_btn.clicked.connect(self._add)
        toolbar.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._edit)
        toolbar.addWidget(self.edit_btn)

        self.toggle_btn = QPushButton("Deactivate")
        self.toggle_btn.clicked.connect(self._toggle_active)
        toolbar.addWidget(self.toggle_btn)

        self.modifiers_btn = QPushButton("Modifiers…")
        self.modifiers_btn.clicked.connect(self._modifiers)
        toolbar.addWidget(self.modifiers_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        tools = QHBoxLayout()
        self.export_btn = QPushButton("CSV Export")
        self.export_btn.clicked.connect(self._export_csv)
        tools.addWidget(self.export_btn)
        self.import_btn = QPushButton("CSV Import")
        self.import_btn.clicked.connect(self._import_csv)
        tools.addWidget(self.import_btn)
        self.bulk_btn = QPushButton("Bulk Price Update")
        self.bulk_btn.clicked.connect(self._bulk)
        tools.addWidget(self.bulk_btn)
        tools.addStretch(1)
        layout.addLayout(tools)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["SKU", "Name", "Category", "Cost", "Price", "Stock?", "Active"])
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_toggle_label)
        layout.addWidget(self.table)

        # defense in depth: service layer still enforces these
        self.gate(self.edit_btn, "products")
        self.gate(self.toggle_btn, "products")
        self.gate(self.modifiers_btn, "products")
        self.gate(self.import_btn, "products")
        self.gate(self.bulk_btn, "products")

    def on_show(self) -> None:
        self._load_categories()
        self.refresh()

    # -- data -------------------------------------------------------------------
    def _load_categories(self) -> None:
        current = self.cat_filter.currentData()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem("All categories", None)
        with self.db() as s:
            cats = [(c.id, c.name) for c in
                    self.svc(s).catalog.list_categories(active_only=False)]
        for cid, cname in cats:
            self.cat_filter.addItem(cname, cid)
        if current is not None:
            idx = self.cat_filter.findData(current)
            self.cat_filter.setCurrentIndex(max(idx, 0))
        self.cat_filter.blockSignals(False)

    def refresh(self) -> None:
        text = self.search.text().strip()
        cat_id = self.cat_filter.currentData()
        with self.db() as s:
            svc = self.svc(s)
            cat_names = {c.id: c.name for c in
                         svc.catalog.list_categories(active_only=False)}
            qy = s.query(models.Product)
            if text:
                like = f"%{text}%"
                qy = qy.filter(or_(models.Product.name.ilike(like),
                                   models.Product.sku.ilike(like),
                                   models.Product.barcode == text))
            if cat_id is not None:
                qy = qy.filter(models.Product.category_id == cat_id)
            prods = qy.order_by(models.Product.name).all()
            rows = [(p.id, p.sku, p.name, cat_names.get(p.category_id, ""),
                     self.money(p.cost_price), self.money(p.sell_price),
                     "Yes" if p.track_stock else "No",
                     "Yes" if p.is_active else "No", p.is_active)
                    for p in prods]

        self.table.setRowCount(0)
        for pid, sku, name, cat, cost, price, stock, active, is_active in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, val in enumerate((sku, name, cat, cost, price, stock, active)):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, pid)
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self._update_toggle_label()

    def _selected(self) -> tuple[int, str, bool] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        id_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        active_item = self.table.item(row, 6)
        if id_item is None:
            return None
        pid = id_item.data(Qt.ItemDataRole.UserRole)
        name = name_item.text() if name_item else ""
        is_active = (active_item.text() == "Yes") if active_item else True
        return pid, name, is_active

    def _update_toggle_label(self) -> None:
        sel = self._selected()
        self.toggle_btn.setText("Deactivate" if sel is None or sel[2]
                                else "Activate")

    # -- actions ------------------------------------------------------------------
    def _add(self) -> None:
        if ProductDialog(self).exec():
            self.refresh()

    def _edit(self) -> None:
        sel = self._selected()
        if sel is None:
            self.warn("Select a product first.")
            return
        if ProductDialog(self, product_id=sel[0]).exec():
            self.refresh()

    def _toggle_active(self) -> None:
        sel = self._selected()
        if sel is None:
            self.warn("Select a product first.")
            return
        pid, name, is_active = sel
        action = "deactivate" if is_active else "activate"
        if not self.confirm(f"{action.capitalize()} “{name}”?"):
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.catalog.set_active(pid, not is_active, actor)
            return True

        if self.safe(do):
            self.refresh()

    def _modifiers(self) -> None:
        sel = self._selected()
        if sel is None:
            self.warn("Select a product first.")
            return
        ProductModifiersDialog(self, sel[0], sel[1]).exec()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export products to CSV", "products.csv",
            "CSV files (*.csv)")
        if not path:
            return

        def do() -> str | None:
            with self.db() as s:
                return self.svc(s).catalog.export_csv()

        text = self.safe(do)
        if text is None:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as e:
            self.error(f"Could not write file:\n{e}")
            return
        self.info(f"Exported to:\n{path}")

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import products from CSV", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except OSError as e:
            self.error(f"Could not read file:\n{e}")
            return
        if not self.confirm(f"Import products from:\n{path}\n\n"
                            "Existing SKUs will be updated."):
            return

        def do() -> dict | None:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                return svc.catalog.import_csv(text, actor)

        result = self.safe(do)
        if result is None:
            return
        msg = (f"Created: {result['created']}\n"
               f"Updated: {result['updated']}")
        errors = result.get("errors") or []
        if errors:
            shown = "\n".join(errors[:5])
            extra = f"\n… and {len(errors) - 5} more." if len(errors) > 5 else ""
            msg += f"\n\nErrors:\n{shown}{extra}"
        self.info(msg, "CSV Import")
        self.refresh()

    def _bulk(self) -> None:
        if BulkPriceDialog(self).exec():
            self.refresh()
