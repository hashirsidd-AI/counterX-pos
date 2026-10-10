"""Customers, suppliers and tax-rate management (simple CRUD)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..utils.money import d, q
from .auth import AuthService


class DirectoryService:
    def __init__(self, session: Session, auth: AuthService):
        self.s = session
        self.auth = auth

    # -- customers --------------------------------------------------------------
    def list_customers(self, query: str = "") -> list[models.Customer]:
        qy = self.s.query(models.Customer).order_by(models.Customer.name)
        if query.strip():
            like = f"%{query.strip()}%"
            qy = qy.filter(or_(models.Customer.name.ilike(like),
                               models.Customer.phone.ilike(like)))
        return qy.all()

    def create_customer(self, user, name: str, phone: str = "",
                        address: str = "", notes: str = "") -> models.Customer:
        self.auth.require(user, "sell")
        if not name.strip():
            raise ValueError("Customer name is required")
        c = models.Customer(name=name.strip(), phone=phone.strip(),
                            address=address.strip(), notes=notes.strip())
        self.s.add(c)
        self.s.flush()
        return c

    def update_customer(self, user, customer_id: int, **fields) -> models.Customer:
        self.auth.require(user, "sell")
        c = self.s.get(models.Customer, customer_id)
        if not c:
            raise ValueError("Customer not found")
        for k, v in fields.items():
            if k in ("name", "phone", "address", "notes") and isinstance(v, str):
                v = v.strip()
            setattr(c, k, v)
        self.s.flush()
        return c

    # -- suppliers --------------------------------------------------------------
    def list_suppliers(self, query: str = "") -> list[models.Supplier]:
        qy = self.s.query(models.Supplier).order_by(models.Supplier.name)
        if query.strip():
            like = f"%{query.strip()}%"
            qy = qy.filter(or_(models.Supplier.name.ilike(like),
                               models.Supplier.phone.ilike(like)))
        return qy.all()

    def create_supplier(self, user, name: str, phone: str = "",
                        address: str = "", notes: str = "") -> models.Supplier:
        self.auth.require(user, "purchases")
        if not name.strip():
            raise ValueError("Supplier name is required")
        sp = models.Supplier(name=name.strip(), phone=phone.strip(),
                             address=address.strip(), notes=notes.strip())
        self.s.add(sp)
        self.s.flush()
        return sp

    def update_supplier(self, user, supplier_id: int, **fields) -> models.Supplier:
        self.auth.require(user, "purchases")
        sp = self.s.get(models.Supplier, supplier_id)
        if not sp:
            raise ValueError("Supplier not found")
        for k, v in fields.items():
            if k in ("name", "phone", "address", "notes") and isinstance(v, str):
                v = v.strip()
            setattr(sp, k, v)
        self.s.flush()
        return sp

    # -- tax rates ---------------------------------------------------------------
    def list_tax_rates(self) -> list[models.TaxRate]:
        return self.s.query(models.TaxRate).order_by(models.TaxRate.name).all()

    def create_tax_rate(self, user, name: str,
                        rate_percent: Decimal) -> models.TaxRate:
        self.auth.require(user, "settings")
        if not name.strip():
            raise ValueError("Tax rate name is required")
        rate = q(rate_percent)
        if rate < 0 or rate > 100:
            raise ValueError("Tax rate must be between 0 and 100")
        tr = models.TaxRate(name=name.strip(), rate_percent=rate)
        self.s.add(tr)
        self.s.flush()
        return tr

    def set_default_tax_rate(self, user, tax_rate_id: int) -> None:
        self.auth.require(user, "settings")
        for tr in self.s.query(models.TaxRate):
            tr.is_default = (tr.id == tax_rate_id)
        self.s.flush()

    def update_tax_rate(self, user, tax_rate_id: int, name: str | None = None,
                        rate_percent: Decimal | None = None) -> models.TaxRate:
        self.auth.require(user, "settings")
        tr = self.s.get(models.TaxRate, tax_rate_id)
        if not tr:
            raise ValueError("Tax rate not found")
        if name is not None:
            if not name.strip():
                raise ValueError("Tax rate name is required")
            tr.name = name.strip()
        if rate_percent is not None:
            rate = q(rate_percent)
            if rate < 0 or rate > 100:
                raise ValueError("Tax rate must be between 0 and 100")
            tr.rate_percent = rate
        self.s.flush()
        return tr

    def delete_tax_rate(self, user, tax_rate_id: int) -> None:
        self.auth.require(user, "settings")
        tr = self.s.get(models.TaxRate, tax_rate_id)
        if not tr:
            raise ValueError("Tax rate not found")
        if tr.is_default:
            raise ValueError("Cannot delete the default tax rate")
        used = self.s.query(models.Product).filter_by(tax_rate_id=tax_rate_id).count()
        if used:
            raise ValueError(f"Tax rate is used by {used} product(s)")
        self.s.delete(tr)
        self.s.flush()
