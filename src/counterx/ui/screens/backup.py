"""Database & Backup screen: manual backups, retention settings, restore."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ...config import BACKUP_DIR
from ..base import BaseScreen, get_setting, set_setting
from ..theme import set_class

RESTORE_WARNING = (
    "Restore will REPLACE the current database with the selected backup.\n\n"
    "A safety backup of the current data is taken first.\n"
    "You should restart the application after restore.\n\n"
    "Continue with the restore?"
)


class BackupScreen(BaseScreen):
    nav_title = "Database & Backup"
    nav_permission = "backup"
    nav_order = 180

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Database & Backup")
        set_class(title, "h1")
        layout.addWidget(title)

        # -- backup now -----------------------------------------------------------
        bar = QHBoxLayout()
        self.backup_btn = QPushButton("Backup Now")
        set_class(self.backup_btn, "primary")
        self.backup_btn.clicked.connect(self._backup_now)
        self.folder_btn = QPushButton("Open Backup Folder")
        self.folder_btn.clicked.connect(self._open_folder)
        bar.addWidget(self.backup_btn)
        bar.addWidget(self.folder_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        # -- settings --------------------------------------------------------------
        settings_bar = QHBoxLayout()
        self.auto_backup = QCheckBox("Automatic backup")
        self.backup_keep = QSpinBox()
        self.backup_keep.setRange(1, 365)
        self.backup_keep.setSuffix(" days")
        self.save_settings_btn = QPushButton("Save")
        self.save_settings_btn.clicked.connect(self._save_settings)
        settings_bar.addWidget(self.auto_backup)
        settings_bar.addWidget(QLabel("Keep backups for:"))
        settings_bar.addWidget(self.backup_keep)
        settings_bar.addWidget(self.save_settings_btn)
        settings_bar.addStretch(1)
        layout.addLayout(settings_bar)

        # -- backup list --------------------------------------------------------------
        list_title = QLabel("Backups")
        set_class(list_title, "h2")
        layout.addWidget(list_title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "File", "Size KB", "SHA256", "Validated"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        restore_bar = QHBoxLayout()
        self.restore_btn = QPushButton("Restore Selected")
        set_class(self.restore_btn, "danger")
        self.restore_btn.clicked.connect(self._restore_selected)
        restore_bar.addWidget(self.restore_btn)
        restore_bar.addStretch(1)
        layout.addLayout(restore_bar)

    def on_show(self) -> None:
        def _do(s):
            return {
                "auto_backup": get_setting(s, "auto_backup", "0") == "1",
                "backup_keep": get_setting(s, "backup_keep", "14"),
            }

        with self.db() as s:
            values = self.safe(_do, s)
        if values is None:
            return
        self.auto_backup.setChecked(values["auto_backup"])
        try:
            self.backup_keep.setValue(int(values["backup_keep"]))
        except (TypeError, ValueError):
            self.backup_keep.setValue(14)
        self._reload()

    # -- helpers ----------------------------------------------------------------
    def _reload(self) -> None:
        def _do(s):
            recs = self.svc(s).backup.list_backups()
            return [{
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")
                              if r.created_at else "",
                "file": Path(r.path).name,
                "path": r.path,
                "size_kb": f"{(r.size_bytes or 0) / 1024:.1f}",
                "sha256": (r.sha256 or "")[:12],
                "validated": "Yes" if r.validated else "No",
            } for r in recs]

        with self.db() as s:
            rows = self.safe(_do, s)
        if rows is None:
            return
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            date_item = QTableWidgetItem(r["created_at"])
            date_item.setData(Qt.ItemDataRole.UserRole, r["path"])
            self.table.setItem(row, 0, date_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["file"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["size_kb"]))
            self.table.setItem(row, 3, QTableWidgetItem(r["sha256"]))
            self.table.setItem(row, 4, QTableWidgetItem(r["validated"]))

    def _selected_path(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            self.warn("Select a backup first.")
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    # -- actions ----------------------------------------------------------------
    def _backup_now(self) -> None:
        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            rec = svc.backup.backup(user=actor, label="manual")
            return rec.path

        with self.db() as s:
            path = self.safe(_do, s)
        if path:
            self.info(f"Backup complete:\n{path}")
            self._reload()

    def _save_settings(self) -> None:
        auto = "1" if self.auto_backup.isChecked() else "0"
        keep = str(self.backup_keep.value())

        def _do(s):
            set_setting(s, "auto_backup", auto)
            set_setting(s, "backup_keep", keep)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Backup settings saved.")

    def _restore_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        if not self.confirm(RESTORE_WARNING, title="Restore Database"):
            return

        def _do(s):
            svc = self.svc(s)
            actor = self.ctx.actor(s)
            svc.backup.restore(path, actor)
            return True

        with self.db() as s:
            ok = self.safe(_do, s)
        if ok:
            self.info("Restore complete. Please restart the application.")
            self._reload()

    def _open_folder(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(BACKUP_DIR)))
        except Exception as e:  # noqa: BLE001
            self.error(f"Could not open the backup folder:\n{e}")
