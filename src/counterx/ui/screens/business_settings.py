"""Business Settings screen: business profile fields and tax-rate directory."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ...utils.money import q
from ..base import BaseScreen, get_setting, set_setting
from ..theme import set_class

BUSINESS_MODES = ("restaurant", "retail")

SETTING_FIELDS = (
    "business_name",
    "business_address",
    "business_city",
    "business_province",
    "business_phone",
    "tax_registration",
    "receipt_footer",
    "currency_symbol",
    "currency_code",
)

FIELD_LABELS = {
    "business_name": "Business name:",
    "business_address": "Address:",
    "business_city": "City:",
    "business_province": "Province:",
    "business_phone": "Phone:",
    "tax_registration": "Tax registration (NTN/STRN):",
    "receipt_footer": "Receipt footer:",
    "currency_symbol": "Currency symbol:",
    "currency_code": "Currency code:",
}


class TaxRateDialog(QDialog):
    """Add / edit a tax rate. Returns .result = (name, Decimal rate_percent)."""

    def __init__(self, parent, name: str = "",
                 rate_percent: Decimal = Decimal("0")):
        super().__init__(parent)
        self.result: tuple[str, Decimal] | None = None
        self.setWindowTitle("Tax Rate" if not name else "Edit Tax Rate")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setText(name)
        self.rate = QDoubleSpinBox()
        self.rate.setRange(0, 100)
        self.rate.setDecimals(2)
        self.rate.setSuffix(" %")
        self.rate.setValue(float(rate_percent or 0))
        form.addRow("Name:", self.name)
        form.addRow("Rate:", self.rate)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #D64545;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.done_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def done_ok(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.error_label.setText("Tax rate name is required.")
            return
        self.result = (name, q(Decimal(str(self.rate.value()))))
        self.accept()


class BusinessSettingsScreen(BaseScreen):
    nav_title = "Business Settings"
    nav_permission = "settings"
    nav_order = 170

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Business Settings")
        set_class(title, "h1")
        layout.addWidget(title)

        form = QFormLayout()
        self.fields: dict[str, QLineEdit] = {}
        for key in SETTING_FIELDS:
            edit = QLineEdit()
            self.fields[key] = edit
            form.addRow(FIELD_LABELS[key], edit)
        self.mode = QComboBox()
        self.mode.addItems(list(BUSINESS_MODES))
        form.addRow("Business mode:", self.mode)
        layout.addLayout(form)

        save_bar = QHBoxLayout()
        self.save_btn = QPushButton("Save Settings")
        set_class(self.save_btn, "primary")
        self.save_btn.clicked.connect(self._save_settings)
        save_bar.addWidget(self.save_btn)
        save_bar.addStretch(1)
        layout.addLayout(save_bar)

        # -- tax rates -----------------------------------------------------------
        tax_title = QLabel("Tax Rates")
        set_class(tax_title, "h2")
        layout.addWidget(tax_title)

        tax_bar = QHBoxLayout()
        self.tax_add = QPushButton("Add")
        set_class(self.tax_add, "primary")
        self.tax_add.clicked.connect(self._tax_add)
        self.tax_edit = QPushButton("Edit")
        self.tax_edit.clicked.connect(self._tax_edit)
        self.tax_delete = QPushButton("Delete")
        self.tax_delete.clicked.connect(self._tax_delete)
        self.tax_default = QPushButton("Set Default")
        self.tax_default.clicked.connect(self._tax_set_default)
        for b in (self.tax_add, self.tax_edit, self.tax_delete,
                  self.tax_default):
            tax_bar.addWidget(b)
        tax_bar.addStretch(1)
        layout.addLayout(tax_bar)

        self.tax_table = QTableWidget(0, 3)
        self.tax_table.setHorizontalHeaderLabels(["Name", "Rate %", "Default"])
        self.tax_table.horizontalHeader().setStretchLastSection(True)
        self.tax_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.tax_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.tax_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.tax_table)

        note = QLabel("Tax rates are configurable. Verify rates and invoice "
                      "requirements with your accountant/tax advisor before "
                      "commercial use.")
        set_class(note, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def on_show(self) -> None:
        def _do(s):
            return {k: get_setting(s, k, "") for k in SETTING_FIELDS} | {
                "business_mode": get_setting(s, "business_mode", "restaurant")}

        with self.db() as s:
            values = self.safe(_do, s)
        if values is None:
            return
        for key, edit in self.fields.items():
            edit.setText(values.get(key, ""))
        mode = values.get("business_mode", "restaurant")
        self.mode.setCurrentText(mode if mode in BUSINESS_MODES else "restaurant")
        self._reload_tax()

    # -- settings ----------------------------------------------------------------
    def _save_settings(self) -> None:
        values = {k: e.text().strip() for k, e in self.fields.items()}
        mode = self.mode.currentText()

        def _do(s):
            for k, v in values.items():
                set_setting(s, k, v)
            set_setting(s, "business_mode", mode)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Settings saved.")

    # -- tax rates ----------------------------------------------------------------
    def _reload_tax(self) -> None:
        def _do(s):
            rates = self.svc(s).directory.list_tax_rates()
            return [{"id": r.id, "name": r.name,
                     "rate_percent": str(r.rate_percent),
                     "is_default": bool(r.is_default)} for r in rates]

        with self.db() as s:
            rows = self.safe(_do, s)
        if rows is None:
            return
        self.tax_table.setRowCount(0)
        for r in rows:
            row = self.tax_table.rowCount()
            self.tax_table.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.tax_table.setItem(row, 0, name_item)
            self.tax_table.setItem(row, 1, QTableWidgetItem(r["rate_percent"]))
            self.tax_table.setItem(row, 2,
                                   QTableWidgetItem("Yes" if r["is_default"] else ""))

    def _selected_tax(self) -> dict | None:
        row = self.tax_table.currentRow()
        if row < 0:
            self.warn("Select a tax rate first.")
            return None
        name_item = self.tax_table.item(row, 0)
        return {
            "id": int(name_item.data(Qt.ItemDataRole.UserRole)),
            "name": name_item.text(),
            "rate_percent": Decimal(self.tax_table.item(row, 1).text()),
        }

    def _tax_add(self) -> None:
        dlg = TaxRateDialog(self)
        if not dlg.exec():
            return
        name, rate = dlg.result

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            svc.directory.create_tax_rate(actor, name, rate)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Tax rate added.")
            self._reload_tax()

    def _tax_edit(self) -> None:
        sel = self._selected_tax()
        if not sel:
            return
        dlg = TaxRateDialog(self, name=sel["name"],
                            rate_percent=sel["rate_percent"])
        if not dlg.exec():
            return
        name, rate = dlg.result
        tax_id = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            svc.directory.update_tax_rate(actor, tax_id, name=name,
                                          rate_percent=rate)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Tax rate updated.")
            self._reload_tax()

    def _tax_delete(self) -> None:
        sel = self._selected_tax()
        if not sel:
            return
        if not self.confirm(f"Delete tax rate '{sel['name']}'?"):
            return
        tax_id = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            svc.directory.delete_tax_rate(actor, tax_id)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Tax rate deleted.")
            self._reload_tax()

    def _tax_set_default(self) -> None:
        sel = self._selected_tax()
        if not sel:
            return
        tax_id = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            svc.directory.set_default_tax_rate(actor, tax_id)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info(f"'{sel['name']}' is now the default tax rate.")
            self._reload_tax()
