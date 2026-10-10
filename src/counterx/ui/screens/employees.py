"""Employees & Permissions screen: manage users and per-user permission overrides."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ... import models
from ...config import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from ..base import BaseScreen
from ..theme import set_class


class UserDialog(QDialog):
    """Add / edit a user. Returns .result dict on accept, None otherwise.

    For a new user, password is required. On edit, a blank password keeps
    the existing one.
    """

    def __init__(self, parent, existing: dict | None = None):
        super().__init__(parent)
        self.existing = existing
        self.result: dict | None = None
        editing = existing is not None
        self.setWindowTitle("Edit User" if editing else "Add User")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username = QLineEdit()
        self.full_name = QLineEdit()
        self.role = QComboBox()
        self.role.addItems(list(ROLES))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.active = QCheckBox("Account is active")

        if editing:
            self.username.setText(existing["username"])
            self.username.setReadOnly(True)
            self.full_name.setText(existing["full_name"])
            self.role.setCurrentText(existing["role"])
            self.password.setPlaceholderText("Leave blank to keep current password")
            self.active.setChecked(existing["is_active"])
        else:
            self.active.setChecked(True)

        form.addRow("Username:", self.username)
        form.addRow("Full name:", self.full_name)
        form.addRow("Role:", self.role)
        form.addRow("Password:", self.password)
        form.addRow("", self.active)
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
        username = self.username.text().strip()
        password = self.password.text()
        role = self.role.currentText()
        if self.existing is None:
            if not username:
                self.error_label.setText("Username is required.")
                return
            if len(password) < 4:
                self.error_label.setText("Password must be at least 4 characters.")
                return
        elif password and len(password) < 4:
            self.error_label.setText("Password must be at least 4 characters.")
            return
        if role not in ROLES:
            self.error_label.setText("Unknown role.")
            return
        self.result = {
            "username": username,
            "full_name": self.full_name.text().strip(),
            "role": role,
            "password": password,
            "active": self.active.isChecked(),
        }
        self.accept()


class ChangePasswordDialog(QDialog):
    """Set a new password for a user. Returns .result (str) or None."""

    def __init__(self, parent, username: str):
        super().__init__(parent)
        self.result: str | None = None
        self.setWindowTitle(f"Change Password — {username}")
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("New password:", self.password)
        form.addRow("Confirm password:", self.confirm)
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
        if len(self.password.text()) < 4:
            self.error_label.setText("Password must be at least 4 characters.")
            return
        if self.password.text() != self.confirm.text():
            self.error_label.setText("Passwords do not match.")
            return
        self.result = self.password.text()
        self.accept()


class PermissionsDialog(QDialog):
    """Per-user permission overrides. Checked = user currently has the perm
    (role default or explicit override). Saving stores an explicit
    grant/revoke override for every permission."""

    def __init__(self, parent, username: str, role: str,
                 current: dict[str, bool]):
        super().__init__(parent)
        self.username = username
        self.role = role
        self.result: dict[str, bool] | None = None
        self.checks: dict[str, QCheckBox] = {}
        self.setWindowTitle(f"Permissions — {username}")
        self.setModal(True)
        self.setMinimumSize(420, 520)

        layout = QVBoxLayout(self)
        title = QLabel(f"Permissions for {username}")
        set_class(title, "h2")
        layout.addWidget(title)
        sub = QLabel(
            f"Role: {role}. Role defaults are applied first; "
            "the checkboxes below show the effective permission. "
            "Saving stores an explicit grant/revoke override for each permission.")
        set_class(sub, "muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        defaults = set(ROLE_PERMISSIONS.get(role, ()))
        for perm in PERMISSIONS:
            box = QCheckBox(perm)
            box.setChecked(bool(current.get(perm, False)))
            self.checks[perm] = box
            row = QHBoxLayout()
            row.addWidget(box)
            hint = QLabel("role default" if perm in defaults else "not in role")
            set_class(hint, "muted")
            row.addStretch(1)
            row.addWidget(hint)
            inner_layout.addLayout(row)
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        set_class(buttons.button(QDialogButtonBox.StandardButton.Ok), "primary")
        buttons.accepted.connect(self.done_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def done_ok(self) -> None:
        self.result = {p: box.isChecked() for p, box in self.checks.items()}
        self.accept()


class EmployeesScreen(BaseScreen):
    nav_title = "Employees & Permissions"
    nav_permission = "users"
    nav_order = 150

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Employees & Permissions")
        set_class(title, "h1")
        layout.addWidget(title)

        bar = QHBoxLayout()
        self.add_btn = QPushButton("Add User")
        set_class(self.add_btn, "primary")
        self.add_btn.clicked.connect(self._add_user)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.clicked.connect(self._edit_user)
        self.toggle_btn = QPushButton("Activate / Deactivate")
        self.toggle_btn.clicked.connect(self._toggle_active)
        self.pw_btn = QPushButton("Change Password")
        self.pw_btn.clicked.connect(self._change_password)
        self.perm_btn = QPushButton("Permissions")
        self.perm_btn.clicked.connect(self._open_permissions)
        for b in (self.add_btn, self.edit_btn, self.toggle_btn,
                  self.pw_btn, self.perm_btn):
            bar.addWidget(b)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Username", "Full Name", "Role", "Active"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        note = QLabel("Owners have all permissions. Roles grant baseline "
                      "permissions; the Permissions dialog can grant or revoke "
                      "individual permissions per user.")
        set_class(note, "muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def on_show(self) -> None:
        self._reload()

    # -- helpers ----------------------------------------------------------------
    def _selected(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            self.warn("Select a user first.")
            return None
        uid_item = self.table.item(row, 0)
        return {
            "id": int(uid_item.data(Qt.ItemDataRole.UserRole)),
            "username": uid_item.text(),
            "full_name": self.table.item(row, 1).text(),
            "role": self.table.item(row, 2).text(),
            "is_active": self.table.item(row, 3).text() == "Yes",
        }

    def _reload(self) -> None:
        def _do(s):
            users = self.svc(s).auth.list_users()
            return [{"id": u.id, "username": u.username,
                     "full_name": u.full_name or "", "role": u.role,
                     "is_active": bool(u.is_active)} for u in users]

        with self.db() as s:
            rows = self.safe(_do, s)
        if rows is None:
            return
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            u_item = QTableWidgetItem(r["username"])
            u_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, u_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["full_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["role"]))
            self.table.setItem(row, 3, QTableWidgetItem(
                "Yes" if r["is_active"] else "No"))

    # -- actions ----------------------------------------------------------------
    def _add_user(self) -> None:
        dlg = UserDialog(self)
        if not dlg.exec():
            return
        data = dlg.result

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            user = svc.auth.create_user(data["username"], data["password"],
                                        full_name=data["full_name"],
                                        role=data["role"], actor=actor)
            if not data["active"]:
                svc.auth.set_active(user, False, actor)
            return user.username

        with self.db() as s:
            name = self.safe(_do, s)
        if name:
            self.info(f"User '{name}' created.")
            self._reload()

    def _edit_user(self) -> None:
        sel = self._selected()
        if not sel:
            return
        dlg = UserDialog(self, existing=sel)
        if not dlg.exec():
            return
        data = dlg.result
        uid = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            user = s.get(models.User, uid)
            if user is None:
                raise ValueError("User not found")
            if data["role"] not in ROLES:
                raise ValueError("Unknown role")
            user.full_name = data["full_name"]
            user.role = data["role"]
            svc.auth.set_active(user, data["active"], actor)
            if data["password"]:
                svc.auth.change_password(user, data["password"], actor)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("User updated.")
            self._reload()

    def _toggle_active(self) -> None:
        sel = self._selected()
        if not sel:
            return
        if sel["username"] == self.ctx.username:
            self.warn("You cannot deactivate your own account.")
            return
        make_active = not sel["is_active"]
        action = "activate" if make_active else "deactivate"
        if not self.confirm(f"{action.capitalize()} user '{sel['username']}'?"):
            return
        uid = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            user = s.get(models.User, uid)
            if user is None:
                raise ValueError("User not found")
            svc.auth.set_active(user, make_active, actor)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info(f"User '{sel['username']}' {action}d.")
            self._reload()

    def _change_password(self) -> None:
        sel = self._selected()
        if not sel:
            return
        dlg = ChangePasswordDialog(self, sel["username"])
        if not dlg.exec():
            return
        new_password = dlg.result
        uid = sel["id"]

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            user = s.get(models.User, uid)
            if user is None:
                raise ValueError("User not found")
            svc.auth.change_password(user, new_password, actor)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Password changed.")

    def _open_permissions(self) -> None:
        sel = self._selected()
        if not sel:
            return
        uid = sel["id"]

        def _load(s):
            svc = self.svc(s)
            user = s.get(models.User, uid)
            if user is None:
                raise ValueError("User not found")
            return {
                "username": user.username,
                "role": user.role,
                "current": {p: svc.auth.has_permission(user, p)
                            for p in PERMISSIONS},
            }

        with self.db() as s:
            data = self.safe(_load, s)
        if not data:
            return
        dlg = PermissionsDialog(self, data["username"], data["role"],
                                data["current"])
        if not dlg.exec():
            return
        desired = dlg.result

        def _save(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            user = s.get(models.User, uid)
            if user is None:
                raise ValueError("User not found")
            for perm, granted in desired.items():
                svc.auth.set_override(user, perm, bool(granted), actor)
            return True

        with self.db() as s:
            ok = self.safe(_save, s)
        if ok:
            self.info("Permission overrides saved.")
