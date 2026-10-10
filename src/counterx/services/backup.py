"""Backup & restore with integrity validation.

- backup(): copies the live DB (via SQLite backup API so it is safe while open),
  records sha256 + size, validates by opening the copy, prunes old backups.
- restore(path): never destroys the only good copy — it first takes a safety
  backup of the current DB, validates the chosen file, then swaps it in.
- report success only after validation.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models
from ..config import BACKUP_DIR, DB_PATH
from .auth import AuthService

log = logging.getLogger("counterx.backup")


class BackupError(Exception):
    pass


class BackupService:
    def __init__(self, session: Session, auth: AuthService,
                 db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR):
        self.s = session
        self.auth = auth
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _sha256(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def _validate_db_file(self, path: Path) -> None:
        """Open the file, run integrity_check and a basic query."""
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if ok != "ok":
                    raise BackupError(f"integrity_check failed: {ok}")
                conn.execute("SELECT count(*) FROM sales").fetchone()
            finally:
                conn.close()
        except BackupError:
            raise
        except Exception as e:  # noqa: BLE001
            raise BackupError(f"Backup file is not a valid database: {e}")

    def backup(self, user=None, label: str = "manual") -> models.BackupRecord:
        if user is not None:
            self.auth.require(user, "backup")
        if not self.db_path.exists():
            raise BackupError("Database file does not exist yet")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.backup_dir / f"counterx_{label}_{stamp}.db"
        # SQLite online backup API: safe copy even while the app is running.
        src = sqlite3.connect(str(self.db_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        self._validate_db_file(dest)  # raises if bad -> no success reported
        rec = models.BackupRecord(path=str(dest), size_bytes=dest.stat().st_size,
                                  sha256=self._sha256(dest), validated=True)
        self.s.add(rec)
        self.s.flush()
        self._prune()
        log.info("Backup OK: %s", dest)
        return rec

    def _prune(self) -> None:
        keep = int(self._setting("backup_keep", "14"))
        recs = (self.s.query(models.BackupRecord)
                .order_by(models.BackupRecord.created_at.desc()).all())
        for rec in recs[keep:]:
            try:
                Path(rec.path).unlink(missing_ok=True)
            except OSError:
                pass
            self.s.delete(rec)
        self.s.flush()

    def list_backups(self) -> list[models.BackupRecord]:
        return (self.s.query(models.BackupRecord)
                .order_by(models.BackupRecord.created_at.desc()).all())

    def restore(self, backup_path: str | Path, user) -> Path:
        """Restore a validated backup. Takes a safety backup of the current DB
        first, and only swaps files after the chosen backup validates."""
        self.auth.require(user, "backup")
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise BackupError("Backup file not found")
        self._validate_db_file(backup_path)  # chosen file must be good first
        safety = None
        if self.db_path.exists():
            safety = self.backup(user, label="pre_restore_safety")
        # swap in the restored file
        tmp = self.db_path.with_suffix(".db.restoring")
        shutil.copy2(backup_path, tmp)
        self._validate_db_file(tmp)
        tmp.replace(self.db_path)
        log.info("Restore OK from %s (safety backup: %s)",
                 backup_path, safety.path if safety else None)
        return self.db_path

    def _setting(self, key: str, default: str) -> str:
        row = self.s.query(models.Setting).filter_by(key=key).first()
        return row.value if row else default
