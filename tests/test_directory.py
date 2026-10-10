"""Tests for DirectoryService: customers, suppliers, tax rates."""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from counterx.services import DirectoryService  # noqa: E402
from counterx.services import PermissionDenied  # noqa: E402


@pytest.fixture()
def directory(db, auth):
    return DirectoryService(db, auth)


def test_customer_crud(directory, owner):
    c = directory.create_customer(owner, "Ahmed Khan", "03001234567", "Lahore")
    assert c.id is not None
    found = directory.list_customers("ahmed")
    assert len(found) == 1 and found[0].phone == "03001234567"
    directory.update_customer(owner, c.id, phone="03217654321")
    assert directory.list_customers()[0].phone == "03217654321"


def test_customer_requires_name(directory, owner):
    with pytest.raises(ValueError):
        directory.create_customer(owner, "  ")


def test_cashier_can_manage_customers(directory, cashier):
    # customers are a POS workflow (sell permission)
    c = directory.create_customer(cashier, "Walk-in")
    assert c.id is not None


def test_cashier_cannot_manage_suppliers(directory, cashier):
    with pytest.raises(PermissionDenied):
        directory.create_supplier(cashier, "Supplier X")


def test_supplier_crud(directory, owner):
    s = directory.create_supplier(owner, "Metro Foods", "042-1234567")
    assert directory.list_suppliers("metro")[0].name == "Metro Foods"
    directory.update_supplier(owner, s.id, address="Lahore")
    assert directory.list_suppliers()[0].address == "Lahore"


def test_tax_rate_lifecycle(directory, owner):
    tr = directory.create_tax_rate(owner, "GST 15%", Decimal("15"))
    assert tr.rate_percent == Decimal("15.00")
    rates = directory.list_tax_rates()
    assert any(r.name == "GST 15%" for r in rates)
    directory.set_default_tax_rate(owner, tr.id)
    defaults = [r for r in directory.list_tax_rates() if r.is_default]
    assert len(defaults) == 1 and defaults[0].id == tr.id
    directory.update_tax_rate(owner, tr.id, rate_percent=Decimal("16"))
    assert directory.list_tax_rates()[0].rate_percent in (Decimal("16.00"),)


def test_tax_rate_validation(directory, owner):
    with pytest.raises(ValueError):
        directory.create_tax_rate(owner, "Bad", Decimal("150"))
    with pytest.raises(ValueError):
        directory.create_tax_rate(owner, "  ", Decimal("5"))


def test_cannot_delete_default_tax_rate(directory, owner):
    default = [r for r in directory.list_tax_rates() if r.is_default][0]
    with pytest.raises(ValueError):
        directory.delete_tax_rate(owner, default.id)


def test_cashier_cannot_manage_tax_rates(directory, cashier):
    with pytest.raises(PermissionDenied):
        directory.create_tax_rate(cashier, "X", Decimal("5"))
