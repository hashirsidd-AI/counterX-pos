"""Pytest fixtures: isolated SQLite DB per test, wired services."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import event  # noqa: E402

from counterx import database, models  # noqa: E402
from counterx.services import (  # noqa: E402
    AuthService, CatalogService, SaleService, InventoryService,
    ShiftService, ReportService, BackupService, LicenseService, PrintService,
)


@pytest.fixture()
def engine(tmp_path):
    eng = database.get_engine(tmp_path / "test.db")
    database.init_db(eng)
    return eng


@pytest.fixture()
def db(engine):
    with database.session_scope(engine) as s:
        yield s


@pytest.fixture()
def auth(db):
    return AuthService(db)


@pytest.fixture()
def owner(db, auth):
    return auth.create_user("owner", "owner1234", "Owner", role="owner")


@pytest.fixture()
def cashier(db, auth):
    return auth.create_user("cashier1", "cash1234", "Cashier One", role="cashier")


@pytest.fixture()
def svcs(db, auth):
    return {
        "auth": auth,
        "catalog": CatalogService(db, auth),
        "sales": SaleService(db, auth),
        "inventory": InventoryService(db, auth),
        "shifts": ShiftService(db, auth),
        "reports": ReportService(db),
        "backup": BackupService(db, auth, db_path=Path(db.get_bind().url.database)),
        "license": LicenseService(db),
        "printing": PrintService(db),
    }
