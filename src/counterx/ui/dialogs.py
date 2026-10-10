"""Modal dialogs: login, first-run wizard, checkout, cash moves, close shift."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QRadioButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from .. import models
from ..config import APP_NAME, COMPANY_NAME, COMPANY_PHONES
from ..database import session_scope
from ..services import AuthService, AuthenticationError
from ..utils.money import d, fmt, q
from . import printing_ui
from .base import get_setting, set_setting
from .theme import set_class


def _spin(max_value: float = 10_000_000.0, decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, max_value)
    s.setDecimals(decimals)
    s.setMinimumWidth(160)
    return s


class LoginDialog(QDialog):
    """Returns .user_id on success, None if cancelled."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.user_id: int | None = None
        self.setWindowTitle(f"{APP_NAME} — Login")
        self.setModal(True)
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        brand = QLabel("◆ CounterX")
        set_class(brand, "brand-dark")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)
        brand_sub = QLabel("POS SOFTWARE COMPANY")
        set_class(brand_sub, "brand-sub-dark")
        brand_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand_sub)
        title = QLabel(APP_NAME)
        set_class(title, "h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Password")
        self.password.returnPressed.connect(self.try_login)
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #D64545;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Login")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.try_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        forgot = QPushButton("Forgot password?")
        forgot.setFlat(True)
        forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot.setStyleSheet("color: #0F9D8A; text-decoration: underline;")
        forgot.clicked.connect(self._forgot_password)
        layout.addWidget(forgot, alignment=Qt.AlignmentFlag.AlignCenter)

    def _forgot_password(self) -> None:
        RecoveryDialog(self.engine, self).exec()

    def try_login(self) -> None:
        try:
            with session_scope(self.engine) as s:
                user = AuthService(s).authenticate(
                    self.username.text(), self.password.text())
                self.user_id = user.id
        except AuthenticationError as e:
            self.error_label.setText(str(e))
            return
        except Exception as e:  # noqa: BLE001
            self.error_label.setText(f"Login failed: {e}")
            return
        self.accept()


class RecoveryDialog(QDialog):
    """Reset the owner password using the one-time owner recovery code."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle(f"{APP_NAME} — Recover owner password")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        info = QLabel("Enter the owner recovery code that was shown once "
                      "during first-time setup, then choose a new password.")
        info.setWordWrap(True)
        set_class(info, "muted")
        layout.addWidget(info)

        form = QFormLayout()
        self.code = QLineEdit()
        self.code.setPlaceholderText("CXRC-XXXX-XXXX-XXXX")
        self.new_password = QLineEdit()
        self.new_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Recovery code:", self.code)
        form.addRow("New password:", self.new_password)
        form.addRow("Confirm password:", self.confirm_password)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #D64545;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Reset password")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.do_reset)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def do_reset(self) -> None:
        code = self.code.text().strip()
        pw1 = self.new_password.text()
        pw2 = self.confirm_password.text()
        if not code:
            self.error_label.setText("Enter the recovery code.")
            return
        if len(pw1) < 4:
            self.error_label.setText("Password must be at least 4 characters.")
            return
        if pw1 != pw2:
            self.error_label.setText("Passwords do not match.")
            return
        try:
            with session_scope(self.engine) as s:
                user = AuthService(s).recover_owner_password(code, pw1)
                username = user.username
        except (AuthenticationError, ValueError) as e:
            self.error_label.setText(str(e))
            return
        QMessageBox.information(
            self, APP_NAME,
            f"Owner password for '{username}' has been reset.\n"
            "Please log in with the new password.")
        self.accept()


class FirstRunWizard(QDialog):
    """Creates the owner account + basic business settings. Returns .user_id."""

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.user_id: int | None = None
        self.setWindowTitle(f"{APP_NAME} — First-time setup")
        self.setModal(True)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        title = QLabel("Welcome to counterX POS")
        set_class(title, "h1")
        layout.addWidget(title)
        sub = QLabel("Set up your business and create the owner account. "
                     "You can change everything later in Business Settings.")
        set_class(sub, "muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        form = QFormLayout()
        self.business_name = QLineEdit()
        self.business_name.setPlaceholderText("e.g. Kohsar Nagar Resort — Restaurant")
        self.business_type = QComboBox()
        self.business_type.addItems(["Restaurant", "Cafe", "Bakery", "Retail"])
        self.business_address = QLineEdit()
        self.business_city = QLineEdit()
        self.business_province = QLineEdit()
        self.business_phone = QLineEdit()
        self.business_phone.setPlaceholderText("03xx-xxxxxxx")
        logo_row = QHBoxLayout()
        self.business_logo = QLineEdit()
        self.business_logo.setReadOnly(True)
        self.business_logo.setPlaceholderText("No logo selected")
        logo_btn = QPushButton("Browse…")
        logo_btn.clicked.connect(self._pick_logo)
        logo_row.addWidget(self.business_logo, 1)
        logo_row.addWidget(logo_btn)
        self.tax_rate = QDoubleSpinBox()
        self.tax_rate.setRange(0, 100)
        self.tax_rate.setDecimals(2)
        self.tax_rate.setSuffix(" %")
        self.receipt_footer = QLineEdit()
        self.receipt_footer.setText("Thank you for your visit!")
        self.auto_backup = QCheckBox("Enable automatic local backup")
        self.auto_backup.setChecked(True)
        self.owner_username = QLineEdit()
        self.owner_username.setText("owner")
        self.owner_password = QLineEdit()
        self.owner_password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Business name:", self.business_name)
        form.addRow("Business type:", self.business_type)
        form.addRow("Business logo:", logo_row)
        form.addRow("Address:", self.business_address)
        form.addRow("City:", self.business_city)
        form.addRow("Province:", self.business_province)
        form.addRow("Phone:", self.business_phone)
        form.addRow("Default tax rate:", self.tax_rate)
        form.addRow("Receipt footer:", self.receipt_footer)
        form.addRow("", self.auto_backup)
        form.addRow("Owner username:", self.owner_username)
        form.addRow("Owner password:", self.owner_password)
        layout.addLayout(form)

        cat_lbl = QLabel("Starting catalogue:")
        set_class(cat_lbl, "h2")
        layout.addWidget(cat_lbl)
        self.demo_radio_sample = QRadioButton(
            "Load sample fast-food menu (recommended)")
        self.demo_radio_sample.setChecked(True)
        self.demo_radio_empty = QRadioButton("Start with empty catalogue")
        layout.addWidget(self.demo_radio_sample)
        layout.addWidget(self.demo_radio_empty)
        demo_hint = QLabel("Sample items are clearly marked and can be edited "
                           "or removed any time from Products & Menu.")
        set_class(demo_hint, "muted")
        demo_hint.setWordWrap(True)
        layout.addWidget(demo_hint)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #D64545;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Finish setup")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.finish)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select business logo", "",
            "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.business_logo.setText(path)

    def finish(self) -> None:
        username = self.owner_username.text().strip()
        password = self.owner_password.text()
        if not username or len(password) < 4:
            self.error_label.setText("Owner username and a password of at least "
                                     "4 characters are required.")
            return
        try:
            with session_scope(self.engine) as s:
                auth = AuthService(s)
                user = auth.create_user(username, password,
                                        full_name="Owner", role="owner", actor=None)
                self.user_id = user.id
                set_setting(s, "business_name", self.business_name.text().strip())
                set_setting(s, "business_type", self.business_type.currentText())
                set_setting(s, "business_logo", self.business_logo.text().strip())
                set_setting(s, "business_address", self.business_address.text().strip())
                set_setting(s, "business_city", self.business_city.text().strip())
                set_setting(s, "business_province", self.business_province.text().strip())
                set_setting(s, "business_phone", self.business_phone.text().strip())
                set_setting(s, "receipt_footer", self.receipt_footer.text().strip())
                set_setting(s, "auto_backup",
                            "1" if self.auto_backup.isChecked() else "0")
                # Default tax rate: update the seeded default row (or create it).
                rate = q(self.tax_rate.value())
                tr = s.query(models.TaxRate).filter_by(is_default=True).first()
                if tr is None:
                    s.add(models.TaxRate(name="Default Tax", rate_percent=rate,
                                         is_default=True))
                else:
                    tr.rate_percent = rate
                recovery_code = auth.set_recovery_code(user)
        except ValueError as e:
            self.error_label.setText(str(e))
            return
        # Optional demo catalogue: never blocks setup on failure.
        if self.demo_radio_sample.isChecked():
            try:
                from ..services.demo_data import seed_demo_menu
                with session_scope(self.engine) as s2:
                    owner = s2.get(models.User, self.user_id)
                    seed_demo_menu(s2, owner)
            except Exception as e:  # noqa: BLE001
                self.error_label.setText(
                    f"Setup is complete, but the sample menu could not be "
                    f"loaded: {e}")
        # Show the owner recovery code exactly once.
        RecoveryCodeDialog(self, recovery_code).exec()
        self.accept()


class RecoveryCodeDialog(QDialog):
    """Shows the owner recovery code ONCE. The code is never shown again."""

    def __init__(self, parent, code: str):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Owner recovery code")
        self.setModal(True)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        warn = QLabel(
            "WRITE THIS CODE DOWN NOW and keep it somewhere safe.\n"
            "It will NEVER be shown again. Anyone with this code can reset "
            "the owner password.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #D64545; font-weight: bold;")
        layout.addWidget(warn)

        code_lbl = QLabel(code)
        code_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        set_class(code_lbl, "h1")
        layout.addWidget(code_lbl)

        hint = QLabel("You can select and copy the code above.")
        set_class(hint, "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "I have written it down")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class CheckoutDialog(QDialog):
    """Collect payment for a cart total. Returns .payments (list of dicts)."""

    def __init__(self, parent, grand_total: Decimal):
        super().__init__(parent)
        self.grand_total = q(grand_total)
        self.payments: list[dict] | None = None
        self.setWindowTitle("Checkout — Payment")
        self.setModal(True)
        self.setMinimumSize(460, 420)

        layout = QVBoxLayout(self)
        total_lbl = QLabel(f"Amount due: {fmt(self.grand_total)}")
        set_class(total_lbl, "h1")
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(total_lbl)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # -- cash tab --
        cash_tab = QWidget()
        cash_layout = QFormLayout(cash_tab)
        self.cash_tendered = _spin()
        self.cash_tendered.setValue(float(self.grand_total))
        self.cash_tendered.valueChanged.connect(self._update_change)
        self.cash_change = QLabel(fmt(0))
        set_class(self.cash_change, "h2")
        cash_layout.addRow("Cash received:", self.cash_tendered)
        cash_layout.addRow("Change due:", self.cash_change)
        quick = QHBoxLayout()
        for denom in ("100", "500", "1000", "5000"):
            b = QPushButton(f"Rs{denom}")
            b.clicked.connect(lambda _=False, v=denom: self.cash_tendered.setValue(
                self.cash_tendered.value() + float(v)))
            quick.addWidget(b)
        cash_layout.addRow("Quick add:", quick)
        self.tabs.addTab(cash_tab, "Cash")

        # -- card tab --
        card_tab = QWidget()
        card_layout = QFormLayout(card_tab)
        self.card_amount = _spin()
        self.card_amount.setValue(float(self.grand_total))
        card_layout.addRow("Card amount:", self.card_amount)
        self.tabs.addTab(card_tab, "Card")

        # -- bank transfer tab --
        bank_tab = QWidget()
        bank_layout = QFormLayout(bank_tab)
        self.bank_amount = _spin()
        self.bank_amount.setValue(float(self.grand_total))
        bank_layout.addRow("Transfer amount:", self.bank_amount)
        self.tabs.addTab(bank_tab, "Bank Transfer")

        # -- split tab --
        split_tab = QWidget()
        split_layout = QVBoxLayout(split_tab)
        self.split_table = QTableWidget(0, 2)
        self.split_table.setHorizontalHeaderLabels(["Method", "Amount"])
        self.split_table.horizontalHeader().setStretchLastSection(True)
        split_layout.addWidget(self.split_table)
        add_row = QHBoxLayout()
        self.split_method = QComboBox()
        self.split_method.addItems(["cash", "card", "bank_transfer"])
        self.split_amount = _spin()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_split_leg)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_split_leg)
        add_row.addWidget(self.split_method)
        add_row.addWidget(self.split_amount)
        add_row.addWidget(add_btn)
        add_row.addWidget(remove_btn)
        split_layout.addLayout(add_row)
        self.split_remaining = QLabel()
        set_class(self.split_remaining, "h2")
        split_layout.addWidget(self.split_remaining)
        self.tabs.addTab(split_tab, "Split")
        self._refresh_split()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Complete Sale")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.complete)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_change()

    # -- split helpers -----------------------------------------------------------
    def _split_legs(self) -> list[dict]:
        legs = []
        for r in range(self.split_table.rowCount()):
            method = self.split_table.item(r, 0).text()
            amount = d(self.split_table.item(r, 1).data(Qt.ItemDataRole.UserRole))
            received = d(self.split_table.item(r, 1).data(Qt.ItemDataRole.UserRole + 1)
                         or amount)
            legs.append({"method": method, "amount": amount, "received": received})
        return legs

    def _add_split_leg(self) -> None:
        method = self.split_method.currentText()
        amount = q(self.split_amount.value())
        if amount <= 0:
            return
        received = amount
        if method == "cash":
            received = amount  # tendered == applied for split legs (no change calc)
        row = self.split_table.rowCount()
        self.split_table.insertRow(row)
        m_item = QTableWidgetItem(method)
        m_item.setFlags(m_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        a_item = QTableWidgetItem(fmt(amount))
        a_item.setData(Qt.ItemDataRole.UserRole, str(amount))
        a_item.setData(Qt.ItemDataRole.UserRole + 1, str(received))
        a_item.setFlags(a_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.split_table.setItem(row, 0, m_item)
        self.split_table.setItem(row, 1, a_item)
        self._refresh_split()

    def _remove_split_leg(self) -> None:
        row = self.split_table.currentRow()
        if row >= 0:
            self.split_table.removeRow(row)
            self._refresh_split()

    def _refresh_split(self) -> None:
        paid = sum((leg["amount"] for leg in self._split_legs()), Decimal("0"))
        remaining = q(self.grand_total - paid)
        self.split_remaining.setText(f"Remaining: {fmt(remaining)}")

    def _update_change(self) -> None:
        tendered = q(self.cash_tendered.value())
        change = q(max(Decimal("0"), tendered - self.grand_total))
        self.cash_change.setText(fmt(change))

    # -- completion ----------------------------------------------------------------
    def complete(self) -> None:
        idx = self.tabs.currentIndex()
        if idx == 0:  # cash
            tendered = q(self.cash_tendered.value())
            if tendered < self.grand_total:
                QMessageBox.warning(self, APP_NAME,
                                    "Cash received is less than the amount due.")
                return
            self.payments = [{"method": "cash", "amount": self.grand_total,
                              "received": tendered}]
        elif idx == 1:  # card
            amount = q(self.card_amount.value())
            if amount < self.grand_total:
                QMessageBox.warning(self, APP_NAME,
                                    "Card amount is less than the amount due.")
                return
            self.payments = [{"method": "card", "amount": self.grand_total}]
        elif idx == 2:  # bank
            amount = q(self.bank_amount.value())
            if amount < self.grand_total:
                QMessageBox.warning(self, APP_NAME,
                                    "Transfer amount is less than the amount due.")
                return
            self.payments = [{"method": "bank_transfer", "amount": self.grand_total}]
        else:  # split
            legs = self._split_legs()
            if not legs:
                QMessageBox.warning(self, APP_NAME, "Add at least one payment leg.")
                return
            paid = q(sum((leg["amount"] for leg in legs), Decimal("0")))
            if paid != self.grand_total:
                QMessageBox.warning(
                    self, APP_NAME,
                    f"Split legs total {fmt(paid)} but the amount due is "
                    f"{fmt(self.grand_total)}. They must match exactly.")
                return
            self.payments = legs
        self.accept()


class CashMoveDialog(QDialog):
    """Cash in / cash out. Returns (amount: Decimal, reason: str) or None."""

    def __init__(self, parent, mode: str):
        super().__init__(parent)
        assert mode in ("cash_in", "cash_out")
        self.mode = mode
        self.result: tuple[Decimal, str] | None = None
        self.setWindowTitle("Cash In" if mode == "cash_in" else "Cash Out")
        self.setModal(True)
        self.setMinimumWidth(360)
        layout = QFormLayout(self)
        self.amount = _spin()
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (optional)")
        layout.addRow("Amount:", self.amount)
        layout.addRow("Reason:", self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.done_ok)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def done_ok(self) -> None:
        amount = q(self.amount.value())
        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Amount must be positive.")
            return
        self.result = (amount, self.reason.text().strip())
        self.accept()


class ExpenseDialog(QDialog):
    """Record an expense. Returns (category, amount, note) or None."""

    def __init__(self, parent):
        super().__init__(parent)
        self.result: tuple[str, Decimal, str] | None = None
        self.setWindowTitle("Record Expense")
        self.setModal(True)
        self.setMinimumWidth(380)
        layout = QFormLayout(self)
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(["General", "Utilities", "Rent", "Salaries",
                                "Supplies", "Maintenance", "Marketing", "Other"])
        self.amount = _spin()
        self.note = QLineEdit()
        layout.addRow("Category:", self.category)
        layout.addRow("Amount:", self.amount)
        layout.addRow("Note:", self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.done_ok)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def done_ok(self) -> None:
        amount = q(self.amount.value())
        if amount <= 0:
            QMessageBox.warning(self, APP_NAME, "Amount must be positive.")
            return
        self.result = (self.category.currentText().strip() or "General",
                       amount, self.note.text().strip())
        self.accept()


class CloseShiftDialog(QDialog):
    """Shows expected cash, takes counted cash, shows variance live."""

    def __init__(self, parent, expected_cash: Decimal):
        super().__init__(parent)
        self.expected_cash = q(expected_cash)
        self.counted: Decimal | None = None
        self.setWindowTitle("Close Shift")
        self.setModal(True)
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)

        info = QLabel(
            f"Expected cash in drawer: {fmt(self.expected_cash)}\n"
            "Count the physical cash and enter the total below.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.counted_spin = _spin(max_value=100_000_000.0)
        self.counted_spin.setValue(float(self.expected_cash))
        self.counted_spin.valueChanged.connect(self._update_variance)
        form.addRow("Counted cash:", self.counted_spin)
        layout.addLayout(form)

        self.variance_label = QLabel()
        set_class(self.variance_label, "h2")
        layout.addWidget(self.variance_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Close Shift")
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.done_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_variance()

    def _update_variance(self) -> None:
        counted = q(self.counted_spin.value())
        variance = q(counted - self.expected_cash)
        if variance == 0:
            text, color = f"Balanced (variance {fmt(variance)})", "#1E9E6A"
        elif variance > 0:
            text, color = f"OVER by {fmt(variance)}", "#D99413"
        else:
            text, color = f"SHORT by {fmt(-variance)}", "#D64545"
        self.variance_label.setText(text)
        self.variance_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def done_ok(self) -> None:
        self.counted = q(self.counted_spin.value())
        self.accept()


class TextPreviewDialog(QDialog):
    """Preview printable text (receipt / KOT / report) with Print / Save."""

    def __init__(self, parent, title: str, text: str, printer_name: str = ""):
        super().__init__(parent)
        self.text = text
        self.printer_name = printer_name
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(520, 560)
        layout = QVBoxLayout(self)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        view.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace;")
        layout.addWidget(view)
        row = QHBoxLayout()
        print_btn = QPushButton("Print")
        set_class(print_btn, "primary")
        print_btn.clicked.connect(self.do_print)
        save_btn = QPushButton("Save to file")
        save_btn.clicked.connect(self.do_save)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        row.addWidget(print_btn)
        row.addWidget(save_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)
        footer = QLabel(f"{COMPANY_NAME}: {', '.join(COMPANY_PHONES)}")
        set_class(footer, "muted")
        layout.addWidget(footer)

    def do_print(self) -> None:
        ok, msg = printing_ui.print_text(self.text, self.printer_name)
        if ok:
            QMessageBox.information(self, APP_NAME, msg)
        else:
            QMessageBox.warning(self, APP_NAME, msg)

    def do_save(self) -> None:
        path = printing_ui.save_text_file(self.text, "document")
        QMessageBox.information(self, APP_NAME, f"Saved to:\n{path}")
