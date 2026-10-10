"""License & About screen: license status, activation, company information."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from ...config import (
    APP_NAME, APP_VERSION, BUILD_NUMBER, COMPANY_NAME, COMPANY_PHONES,
)
from ..base import BaseScreen
from ..theme import set_class

STATE_TEXT = {
    "active": "Active",
    "unlicensed": "Unlicensed",
    "expired": "Expired",
    "invalid": "Invalid",
}

STATE_COLOR = {
    "active": "#1E9E6A",
    "unlicensed": "#D64545",
    "expired": "#D99413",
    "invalid": "#D64545",
}


class LicenseScreen(BaseScreen):
    nav_title = "License & About"
    nav_permission = None
    nav_order = 190

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("License & About")
        set_class(title, "h1")
        layout.addWidget(title)

        # -- license status card ----------------------------------------------------
        status_card = QFrame()
        set_class(status_card, "card")
        status_card.setLayout(QVBoxLayout())
        card_title = QLabel("License Status")
        set_class(card_title, "h2")
        status_card.layout().addWidget(card_title)

        status_form = QFormLayout()
        self.state_label = QLabel("")
        status_form.addRow("Status:", self.state_label)
        self.issued_to_label = QLabel("")
        status_form.addRow("Issued to:", self.issued_to_label)
        self.valid_until_label = QLabel("")
        status_form.addRow("Valid until:", self.valid_until_label)
        status_card.layout().addLayout(status_form)

        activation_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("Enter license key (CX1-...)")
        self.activate_btn = QPushButton("Activate")
        set_class(self.activate_btn, "primary")
        self.activate_btn.clicked.connect(self._activate)
        activation_row.addWidget(self.key_edit, 1)
        activation_row.addWidget(self.activate_btn)
        status_card.layout().addLayout(activation_row)

        # Cashiers can view the status but may not activate.
        self.gate(self.key_edit, "license")
        self.gate(self.activate_btn, "license")

        layout.addWidget(status_card)

        # -- about card --------------------------------------------------------------
        about_card = QFrame()
        set_class(about_card, "card")
        about_card.setLayout(QVBoxLayout())
        about_title = QLabel("About")
        set_class(about_title, "h2")
        about_card.layout().addWidget(about_title)

        about_form = QFormLayout()
        about_form.addRow("Product:", QLabel(APP_NAME))
        about_form.addRow("Version:", QLabel(f"{APP_VERSION} (build {BUILD_NUMBER})"))
        about_form.addRow("Company:", QLabel(COMPANY_NAME))
        about_form.addRow("Support:", QLabel(", ".join(COMPANY_PHONES)))
        about_card.layout().addLayout(about_form)
        layout.addWidget(about_card)

        note = QLabel("Licensing is verified offline on this computer. It "
                      "identifies this installation and its expiry; like any "
                      "offline check it does not prevent a determined technical "
                      "user from bypassing it.")
        set_class(note, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)

    def on_show(self) -> None:
        self._refresh_status()

    # -- helpers ----------------------------------------------------------------
    def _refresh_status(self) -> None:
        def _do(s):
            return self.svc(s).licensing.status()

        with self.db() as s:
            status = self.safe(_do, s)
        if status is None:
            return
        state = status.get("state", "unlicensed")
        self.state_label.setText(STATE_TEXT.get(state, state))
        self.state_label.setStyleSheet(
            f"color: {STATE_COLOR.get(state, '#D64545')}; font-weight: 700;")
        self.issued_to_label.setText(status.get("issued_to") or "—")
        valid_until = status.get("valid_until") or ""
        self.valid_until_label.setText(
            valid_until if valid_until else "Perpetual" if state == "active" else "—")

    # -- actions ----------------------------------------------------------------
    def _activate(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.warn("Enter a license key first.")
            return

        def _do(s):
            return self.svc(s).licensing.activate(key)

        with self.db() as s:
            status = self.safe(_do, s)
        if status is None:
            return
        self.key_edit.clear()
        self._refresh_status()
        self.info(f"License activated for {status.get('issued_to', '')}.")
