"""Categories & modifiers management screen."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ... import models
from ...utils.money import d, q
from ..base import BaseScreen
from ..theme import set_class


class CategoryDialog(QDialog):
    """Add / rename a category (name + optional Urdu name)."""

    def __init__(self, screen: "CategoriesScreen", name: str = "",
                 name_ur: str = ""):
        super().__init__(screen)
        self.setWindowTitle("Rename Category" if name else "Add Category")
        self.setModal(True)
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("e.g. Fast Food")
        self.name_ur_edit = QLineEdit(name_ur)
        self.name_ur_edit.setPlaceholderText("اردو نام")
        form.addRow("Name *:", self.name_edit)
        form.addRow("Urdu name:", self.name_ur_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def name_value(self) -> str:
        return self.name_edit.text().strip()

    @property
    def name_ur_value(self) -> str:
        return self.name_ur_edit.text().strip()

    def _ok(self) -> None:
        if not self.name_value:
            self.name_edit.setFocus()
            return
        self.accept()


class ModifierDialog(QDialog):
    """Add / edit a modifier (name + price)."""

    def __init__(self, screen: "CategoriesScreen", name: str = "",
                 price: float = 0.0):
        super().__init__(screen)
        self.setWindowTitle("Edit Modifier" if name else "Add Modifier")
        self.setModal(True)
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("e.g. Extra Cheese")
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 10_000_000.0)
        self.price_spin.setDecimals(2)
        self.price_spin.setValue(price)
        form.addRow("Name *:", self.name_edit)
        form.addRow("Price:", self.price_spin)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def name_value(self) -> str:
        return self.name_edit.text().strip()

    @property
    def price_value(self):
        return q(d(str(self.price_spin.value())))

    def _ok(self) -> None:
        if not self.name_value:
            self.name_edit.setFocus()
            return
        self.accept()


class CategoriesScreen(BaseScreen):
    nav_title = "Categories & Modifiers"
    nav_permission = "products"
    nav_order = 40

    # -- UI -------------------------------------------------------------------
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Categories & Modifiers")
        set_class(title, "h1")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # -- categories tab --
        cat_tab = QWidget()
        cat_layout = QVBoxLayout(cat_tab)
        self.cat_table = QTableWidget(0, 3)
        self.cat_table.setHorizontalHeaderLabels(["Name", "Urdu Name", "Active"])
        self._setup_table(self.cat_table)
        self.cat_table.itemSelectionChanged.connect(self._update_cat_toggle)
        cat_layout.addWidget(self.cat_table)

        cat_btns = QHBoxLayout()
        self.cat_add = QPushButton("Add")
        set_class(self.cat_add, "primary")
        self.cat_add.clicked.connect(self._cat_add)
        cat_btns.addWidget(self.cat_add)
        self.cat_rename = QPushButton("Rename")
        self.cat_rename.clicked.connect(self._cat_rename)
        cat_btns.addWidget(self.cat_rename)
        self.cat_toggle = QPushButton("Deactivate")
        self.cat_toggle.clicked.connect(self._cat_toggle)
        cat_btns.addWidget(self.cat_toggle)
        cat_btns.addStretch(1)
        cat_layout.addLayout(cat_btns)
        self.tabs.addTab(cat_tab, "Categories")

        # -- modifiers tab --
        mod_tab = QWidget()
        mod_layout = QVBoxLayout(mod_tab)
        self.mod_table = QTableWidget(0, 3)
        self.mod_table.setHorizontalHeaderLabels(["Name", "Price", "Active"])
        self._setup_table(self.mod_table)
        mod_layout.addWidget(self.mod_table)

        mod_btns = QHBoxLayout()
        self.mod_add = QPushButton("Add")
        set_class(self.mod_add, "primary")
        self.mod_add.clicked.connect(self._mod_add)
        mod_btns.addWidget(self.mod_add)
        self.mod_edit = QPushButton("Edit")
        self.mod_edit.clicked.connect(self._mod_edit)
        mod_btns.addWidget(self.mod_edit)
        self.mod_toggle = QPushButton("Deactivate")
        self.mod_toggle.clicked.connect(self._mod_toggle)
        mod_btns.addWidget(self.mod_toggle)
        self.mod_delete = QPushButton("Delete")
        set_class(self.mod_delete, "danger")
        self.mod_delete.clicked.connect(self._mod_delete)
        mod_btns.addWidget(self.mod_delete)
        mod_btns.addStretch(1)
        mod_layout.addLayout(mod_btns)
        self.tabs.addTab(mod_tab, "Modifiers")

        # defense in depth: service layer still enforces these
        self.gate(self.cat_rename, "products")
        self.gate(self.cat_toggle, "products")
        self.gate(self.mod_edit, "products")
        self.gate(self.mod_toggle, "products")
        self.gate(self.mod_delete, "products")

    def _setup_table(self, table: QTableWidget) -> None:
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)

    def on_show(self) -> None:
        self._refresh_categories()
        self._refresh_modifiers()

    # -- categories --------------------------------------------------------------
    def _refresh_categories(self) -> None:
        with self.db() as s:
            rows = [(c.id, c.name, c.name_ur or "", c.is_active) for c in
                    self.svc(s).catalog.list_categories(active_only=False)]
        self.cat_table.setRowCount(0)
        for cid, name, name_ur, active in rows:
            r = self.cat_table.rowCount()
            self.cat_table.insertRow(r)
            id_item = QTableWidgetItem(name)
            id_item.setData(Qt.ItemDataRole.UserRole, cid)
            self.cat_table.setItem(r, 0, id_item)
            self.cat_table.setItem(r, 1, QTableWidgetItem(name_ur))
            self.cat_table.setItem(r, 2, QTableWidgetItem("Yes" if active else "No"))
        self.cat_table.resizeColumnsToContents()
        self._update_cat_toggle()

    def _selected_category(self) -> tuple[int, str, str, bool] | None:
        row = self.cat_table.currentRow()
        if row < 0:
            return None
        id_item = self.cat_table.item(row, 0)
        if id_item is None:
            return None
        cid = id_item.data(Qt.ItemDataRole.UserRole)
        name = id_item.text()
        name_ur = (self.cat_table.item(row, 1).text()
                   if self.cat_table.item(row, 1) else "")
        active = (self.cat_table.item(row, 2).text() == "Yes"
                  if self.cat_table.item(row, 2) else True)
        return cid, name, name_ur, active

    def _update_cat_toggle(self) -> None:
        sel = self._selected_category()
        self.cat_toggle.setText("Deactivate" if sel is None or sel[3]
                                else "Activate")

    def _cat_add(self) -> None:
        dlg = CategoryDialog(self)
        if not dlg.exec():
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.catalog.create_category(dlg.name_value, actor,
                                            name_ur=dlg.name_ur_value)
            return True

        if self.safe(do):
            self._refresh_categories()

    def _cat_rename(self) -> None:
        sel = self._selected_category()
        if sel is None:
            self.warn("Select a category first.")
            return
        cid, name, name_ur, _active = sel
        dlg = CategoryDialog(self, name=name, name_ur=name_ur)
        if not dlg.exec():
            return
        new_name, new_ur = dlg.name_value, dlg.name_ur_value

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.auth.require(actor, "products")
                cat = s.get(models.Category, cid)
                if cat is None:
                    raise ValueError("Category not found")
                cat.name = new_name
                cat.name_ur = new_ur
            return True

        if self.safe(do):
            self._refresh_categories()

    def _cat_toggle(self) -> None:
        sel = self._selected_category()
        if sel is None:
            self.warn("Select a category first.")
            return
        cid, name, _ur, active = sel
        action = "deactivate" if active else "activate"
        if not self.confirm(f"{action.capitalize()} category “{name}”?"):
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.auth.require(actor, "products")
                cat = s.get(models.Category, cid)
                if cat is None:
                    raise ValueError("Category not found")
                cat.is_active = not active
            return True

        if self.safe(do):
            self._refresh_categories()

    # -- modifiers ---------------------------------------------------------------
    def _refresh_modifiers(self) -> None:
        with self.db() as s:
            rows = [(m.id, m.name, m.price, m.is_active) for m in
                    s.query(models.Modifier)
                    .order_by(models.Modifier.name).all()]
        self.mod_table.setRowCount(0)
        for mid, name, price, active in rows:
            r = self.mod_table.rowCount()
            self.mod_table.insertRow(r)
            id_item = QTableWidgetItem(name)
            id_item.setData(Qt.ItemDataRole.UserRole, mid)
            self.mod_table.setItem(r, 0, id_item)
            self.mod_table.setItem(r, 1, QTableWidgetItem(self.money(price)))
            self.mod_table.setItem(r, 2, QTableWidgetItem("Yes" if active else "No"))
        self.mod_table.resizeColumnsToContents()
        sel = self._selected_modifier()
        self.mod_toggle.setText("Deactivate" if sel is None or sel[3]
                                else "Activate")

    def _selected_modifier(self) -> tuple[int, str, float, bool] | None:
        row = self.mod_table.currentRow()
        if row < 0:
            return None
        id_item = self.mod_table.item(row, 0)
        if id_item is None:
            return None
        mid = id_item.data(Qt.ItemDataRole.UserRole)
        name = id_item.text()
        active = (self.mod_table.item(row, 2).text() == "Yes"
                  if self.mod_table.item(row, 2) else True)
        price = 0.0
        with self.db() as s:
            m = s.get(models.Modifier, mid)
            if m is not None:
                price = float(m.price or 0)
        return mid, name, price, active

    def _mod_add(self) -> None:
        dlg = ModifierDialog(self)
        if not dlg.exec():
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.catalog.create_modifier(dlg.name_value, dlg.price_value,
                                            actor)
            return True

        if self.safe(do):
            self._refresh_modifiers()

    def _mod_edit(self) -> None:
        sel = self._selected_modifier()
        if sel is None:
            self.warn("Select a modifier first.")
            return
        mid, name, price, _active = sel
        dlg = ModifierDialog(self, name=name, price=price)
        if not dlg.exec():
            return
        new_name, new_price = dlg.name_value, dlg.price_value

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.auth.require(actor, "products")
                m = s.get(models.Modifier, mid)
                if m is None:
                    raise ValueError("Modifier not found")
                m.name = new_name
                m.price = new_price
            return True

        if self.safe(do):
            self._refresh_modifiers()

    def _mod_toggle(self) -> None:
        sel = self._selected_modifier()
        if sel is None:
            self.warn("Select a modifier first.")
            return
        mid, name, _price, active = sel
        action = "deactivate" if active else "activate"
        if not self.confirm(f"{action.capitalize()} modifier “{name}”?"):
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.auth.require(actor, "products")
                m = s.get(models.Modifier, mid)
                if m is None:
                    raise ValueError("Modifier not found")
                m.is_active = not active
            return True

        if self.safe(do):
            self._refresh_modifiers()

    def _mod_delete(self) -> None:
        sel = self._selected_modifier()
        if sel is None:
            self.warn("Select a modifier first.")
            return
        mid, name, _price, _active = sel
        with self.db() as s:
            used = s.query(models.ProductModifier).filter_by(
                modifier_id=mid).count()
        if used:
            self.warn(f"Cannot delete “{name}” — it is attached to "
                      f"{used} product(s).")
            return
        if not self.confirm(f"Delete modifier “{name}” permanently?"):
            return

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                svc.auth.require(actor, "products")
                m = s.get(models.Modifier, mid)
                if m is not None:
                    s.delete(m)
            return True

        if self.safe(do):
            self._refresh_modifiers()
