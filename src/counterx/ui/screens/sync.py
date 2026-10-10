"""Cloud Sync screen: optional offline-first Supabase synchronization.

Local SQLite is always the system of record. This screen configures the
optional cloud connection, shows sync health, and lets the owner trigger
uploads manually. Billing never waits for the cloud.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ... import models
from ...sync import SyncService, SyncError
from ..base import BaseScreen
from ..theme import set_class

BANNER_TEXT = (
    "Cloud sync is optional. Billing, shifts and reports work fully offline. "
    "Local data is never deleted because an upload failed."
)


class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)


def _run_background(fn, on_done, on_error):
    """Run fn() off the UI thread; deliver the result via Qt signals."""
    sig = _Signals()

    def _show_error(msg: str):
        on_error(msg)

    sig.done.connect(on_done)
    sig.error.connect(_show_error)

    def _target():
        try:
            result = fn()
        except Exception as e:  # noqa: BLE001
            sig.error.emit(str(e))
        else:
            sig.done.emit(result)

    threading.Thread(target=_target, daemon=True).start()
    return sig  # keep a reference so it is not garbage-collected


class SyncScreen(BaseScreen):
    nav_title = "Cloud Sync"
    nav_permission = "settings"
    nav_order = 185

    def __init__(self, ctx, parent=None):
        self._sig = None  # background-task signal holder
        super().__init__(ctx, parent)

    # -- UI ----------------------------------------------------------------------
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Cloud Sync")
        set_class(title, "h1")
        layout.addWidget(title)

        banner = QLabel(BANNER_TEXT)
        banner.setWordWrap(True)
        set_class(banner, "muted")
        layout.addWidget(banner)

        # -- status card -----------------------------------------------------------
        status_card = QFrame()
        set_class(status_card, "card")
        status_layout = QVBoxLayout(status_card)
        status_head = QLabel("Sync Status")
        set_class(status_head, "h2")
        status_layout.addWidget(status_head)

        form = QFormLayout()
        self.status_enabled = QLabel("—")
        self.status_configured = QLabel("—")
        id_row = QHBoxLayout()
        self.installation_id = QLabel("—")
        self.installation_id.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy_installation_id)
        id_row.addWidget(self.installation_id, 1)
        id_row.addWidget(copy_btn)
        self.last_sync = QLabel("—")
        self.pending_count = QLabel("—")
        self.failed_count = QLabel("—")
        self.last_error = QLabel("—")
        self.last_error.setWordWrap(True)
        form.addRow("Sync enabled:", self.status_enabled)
        form.addRow("Cloud configured:", self.status_configured)
        form.addRow("Installation ID:", id_row)
        form.addRow("Last successful sync:", self.last_sync)
        form.addRow("Pending uploads:", self.pending_count)
        form.addRow("Failed uploads:", self.failed_count)
        form.addRow("Last error:", self.last_error)
        status_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.sync_now_btn = QPushButton("Sync Now")
        set_class(self.sync_now_btn, "primary")
        self.sync_now_btn.clicked.connect(self._sync_now)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.on_show)
        btn_row.addWidget(self.sync_now_btn)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch(1)
        status_layout.addLayout(btn_row)
        layout.addWidget(status_card)

        # -- connection card --------------------------------------------------------
        conn_card = QFrame()
        set_class(conn_card, "card")
        conn_layout = QVBoxLayout(conn_card)
        conn_head = QLabel("Cloud Connection")
        set_class(conn_head, "h2")
        conn_layout.addWidget(conn_head)
        conn_note = QLabel(
            "Enter your Supabase project URL and anon key. The anon key is "
            "public by design; access is controlled by Row Level Security so "
            "one business can never see another's data. The service-role key "
            "is never used or stored here.")
        conn_note.setWordWrap(True)
        set_class(conn_note, "muted")
        conn_layout.addWidget(conn_note)

        conn_form = QFormLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://xyzcompany.supabase.co")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Supabase anon key")
        self.enabled_check = QCheckBox("Enable cloud sync")
        conn_form.addRow("Supabase URL:", self.url_edit)
        conn_form.addRow("Anon key:", self.key_edit)
        conn_form.addRow("", self.enabled_check)
        conn_layout.addLayout(conn_form)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save & Connect")
        set_class(self.save_btn, "primary")
        self.save_btn.clicked.connect(self._save_and_connect)
        self.working_label = QLabel("")
        set_class(self.working_label, "muted")
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.working_label)
        save_row.addStretch(1)
        conn_layout.addLayout(save_row)
        layout.addWidget(conn_card)

        # -- failed uploads ----------------------------------------------------------
        fail_head_row = QHBoxLayout()
        fail_title = QLabel("Failed Uploads")
        set_class(fail_title, "h2")
        self.retry_btn = QPushButton("Retry now")
        self.retry_btn.clicked.connect(self._retry_failed)
        fail_head_row.addWidget(fail_title)
        fail_head_row.addStretch(1)
        fail_head_row.addWidget(self.retry_btn)
        layout.addLayout(fail_head_row)

        self.fail_table = QTableWidget(0, 4)
        self.fail_table.setHorizontalHeaderLabels(
            ["Entity", "Queued at", "Attempts", "Error"])
        self.fail_table.horizontalHeader().setStretchLastSection(True)
        self.fail_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.fail_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.fail_table)
        layout.addStretch(1)

    def on_show(self) -> None:
        self._refresh()

    # -- data ----------------------------------------------------------------------
    def _refresh(self) -> None:
        def _do():
            with self.db() as s:
                svc = SyncService(self.ctx.engine)
                status = svc.status(s)
                state = svc.get_state(s)
                # Extract plain values inside the session: the ORM row must
                # not be touched after the session closes.
                cloud_url = state.cloud_url or ""
                failed = (s.query(models.SyncQueue)
                          .filter_by(status="failed")
                          .order_by(models.SyncQueue.created_at.desc())
                          .limit(50).all())
                failed_rows = [{
                    "entity": r.entity,
                    "created_at": r.created_at,
                    "attempts": r.attempts,
                    "last_error": r.last_error or "",
                } for r in failed]
                return status, cloud_url, failed_rows

        res = self.safe(_do)
        if res is None:
            return
        status, cloud_url, failed_rows = res
        self.status_enabled.setText("Yes" if status["enabled"] else "No")
        self.status_configured.setText("Yes" if status["configured"] else "No")
        self.installation_id.setText(status["installation_id"])
        self.last_sync.setText(
            status["last_sync_at"].strftime("%d-%m-%Y %H:%M")
            if status["last_sync_at"] else "Never")
        self.pending_count.setText(str(status["pending"]))
        self.failed_count.setText(str(status["failed"]))
        self.last_error.setText(status["last_error"] or "—")
        if not self.url_edit.text():
            self.url_edit.setText(cloud_url)
        self.enabled_check.setChecked(bool(status["enabled"]))

        self.fail_table.setRowCount(0)
        for r in failed_rows:
            row = self.fail_table.rowCount()
            self.fail_table.insertRow(row)
            self.fail_table.setItem(row, 0, QTableWidgetItem(r["entity"]))
            self.fail_table.setItem(
                row, 1, QTableWidgetItem(
                    r["created_at"].strftime("%d-%m-%Y %H:%M")
                    if r["created_at"] else ""))
            self.fail_table.setItem(row, 2, QTableWidgetItem(str(r["attempts"])))
            self.fail_table.setItem(row, 3, QTableWidgetItem(r["last_error"]))

    def _copy_installation_id(self) -> None:
        text = self.installation_id.text()
        if text and text != "—":
            QApplication.clipboard().setText(text)
            self.info("Installation ID copied to clipboard.")

    # -- actions ----------------------------------------------------------------------
    def _set_working(self, working: bool, text: str = "Working…") -> None:
        self.working_label.setText(text if working else "")
        for w in (self.save_btn, self.sync_now_btn, self.retry_btn):
            w.setEnabled(not working)

    def _save_and_connect(self) -> None:
        url = self.url_edit.text().strip()
        key = self.key_edit.text().strip()
        enabled = self.enabled_check.isChecked()
        if enabled and (not url or not key):
            self.warn("Enter the Supabase URL and anon key to enable sync, "
                      "or uncheck 'Enable cloud sync' to save it disabled.")
            return
        self._set_working(True, "Saving…")

        def _do():
            with self.db() as s:
                svc = SyncService(self.ctx.engine)
                svc.configure(s, url, key, enabled)
                info = None
                if enabled:
                    info = svc.connect_cloud_account(s)
                return info

        def _on_done(info):
            self._set_working(False)
            if info:
                self.info(f"Connected to cloud as:\n{info.get('email', '')}\n\n"
                          "Sync is enabled. Uploads happen automatically in "
                          "the background; billing never waits for the cloud.")
            else:
                self.info("Cloud configuration saved (sync disabled).")
            self.key_edit.clear()
            self._refresh()

        def _on_error(msg):
            self._set_working(False)
            # Configuration was already saved; only the connection failed.
            self.warn(f"Configuration saved, but cloud connection failed:\n{msg}")
            self._refresh()

        self._sig = _run_background(_do, _on_done, _on_error)

    def _sync_now(self) -> None:
        self._set_working(True, "Syncing…")

        def _do():
            return SyncService(self.ctx.engine).sync_once()

        def _on_done(result):
            self._set_working(False)
            if result.skipped:
                self.info(f"Sync skipped: {result.message}")
            else:
                self.info(f"Sync finished.\nUploaded: {result.uploaded}\n"
                          f"Failed: {result.failed}")
            self._refresh()

        def _on_error(msg):
            self._set_working(False)
            self.error(f"Sync failed unexpectedly:\n{msg}")
            self._refresh()

        self._sig = _run_background(_do, _on_done, _on_error)

    def _retry_failed(self) -> None:
        def _do():
            with self.db() as s:
                rows = (s.query(models.SyncQueue)
                        .filter_by(status="failed").all())
                n = 0
                for r in rows:
                    r.status = "pending"
                    r.attempts = 0
                    r.last_error = ""
                    r.next_retry_at = None
                    n += 1
                s.flush()
                return n

        n = self.safe(_do)
        if n is None:
            return
        if n == 0:
            self.info("No failed uploads to retry.")
            return
        self._sync_now()
