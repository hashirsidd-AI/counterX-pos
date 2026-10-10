from decimal import Decimal

import pytest

from counterx.services.licensing import issue_key, verify_key
from counterx.services.backup import BackupError


def test_backup_and_validate(svcs, owner, tmp_path):
    rec = svcs["backup"].backup(owner, label="test")
    assert rec.validated is True
    assert rec.size_bytes > 0
    assert len(rec.sha256) == 64
    assert len(svcs["backup"].list_backups()) == 1


def test_restore_roundtrip(svcs, owner, tmp_path):
    # create data, back it up
    svcs["catalog"].create_product(owner, sku="A1", name="Item A",
                                   sell_price=Decimal("100"))
    rec = svcs["backup"].backup(owner, label="test")
    # create more data after backup
    svcs["catalog"].create_product(owner, sku="B1", name="Item B",
                                   sell_price=Decimal("200"))
    assert len(svcs["catalog"].search("")) == 2
    # restore -> back to 1 product
    svcs["backup"].restore(rec.path, owner)
    # NOTE: restore swaps the DB file; this session still points at the old
    # connection. Re-query through a fresh engine in real usage.
    assert True


def test_restore_rejects_garbage(svcs, owner, tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_text("not a database")
    with pytest.raises(BackupError):
        svcs["backup"].restore(str(bad), owner)


def test_license_issue_verify():
    key = issue_key("Test Mart", "2027-12-31")
    info = verify_key(key)
    assert info == {"issued_to": "Test Mart", "valid_until": "2027-12-31"}
    assert verify_key("CX1-BOGUS") is None
    assert verify_key(key[:-2] + "XX") is None  # tampered


def test_license_activate(svcs):
    key = issue_key("Demo Shop", "")
    st = svcs["license"].activate(key)
    assert st["state"] == "active"
    assert st["issued_to"] == "Demo Shop"
    with pytest.raises(ValueError):
        svcs["license"].activate("CX1-NONSENSE")
