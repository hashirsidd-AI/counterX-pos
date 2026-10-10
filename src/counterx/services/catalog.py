"""Product / menu management: categories, products, variants, modifiers, CSV I/O."""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import models
from ..sync.service import enqueue_obj
from ..utils.money import d, q
from .auth import AuthService


class CatalogService:
    def __init__(self, session: Session, auth: AuthService):
        self.s = session
        self.auth = auth

    # -- categories ---------------------------------------------------------------
    def create_category(self, name: str, user, name_ur: str = "",
                        parent_id: int | None = None) -> models.Category:
        self.auth.require(user, "products")
        cat = models.Category(name=name.strip(), name_ur=name_ur, parent_id=parent_id)
        self.s.add(cat)
        self.s.flush()
        enqueue_obj(self.s, "categories", cat)
        return cat

    def list_categories(self, active_only: bool = True) -> list[models.Category]:
        qy = self.s.query(models.Category).order_by(models.Category.sort_order,
                                                    models.Category.name)
        if active_only:
            qy = qy.filter_by(is_active=True)
        return qy.all()

    # -- products -------------------------------------------------------------------
    def generate_sku(self) -> str:
        """Return a unique SKU like ``P-00042``.

        Based on (max product id + 1); walks forward on collision and falls
        back to a timestamp-derived number when the table is empty.
        """
        import time
        max_id = self.s.query(func.max(models.Product.id)).scalar()
        n = (max_id + 1) if max_id else int(time.time()) % 100000
        while True:
            sku = f"P-{n:05d}"
            if not self.s.query(models.Product).filter_by(sku=sku).first():
                return sku
            n += 1

    def create_product(self, user, *, sku: str, name: str, sell_price: Decimal,
                       category_id: int | None = None, barcode: str | None = None,
                       cost_price: Decimal = Decimal("0"), name_ur: str = "",
                       description: str = "", tax_rate_id: int | None = None,
                       track_stock: bool = True, min_stock: Decimal = Decimal("0"),
                       image_path: str = "") -> models.Product:
        self.auth.require(user, "products")
        sku = sku.strip()
        if not sku or not name.strip():
            raise ValueError("SKU and name are required")
        if self.s.query(models.Product).filter_by(sku=sku).first():
            raise ValueError(f"SKU already exists: {sku}")
        if barcode and self.s.query(models.Product).filter_by(barcode=barcode).first():
            raise ValueError(f"Barcode already exists: {barcode}")
        tax_rate_id = tax_rate_id or self._default_tax_id()
        prod = models.Product(
            sku=sku, barcode=barcode or None, name=name.strip(), name_ur=name_ur,
            description=description, category_id=category_id,
            cost_price=q(cost_price), sell_price=q(sell_price),
            tax_rate_id=tax_rate_id, track_stock=track_stock,
            min_stock=q(min_stock), image_path=image_path)
        self.s.add(prod)
        self.s.flush()
        enqueue_obj(self.s, "products", prod)
        return prod

    def update_product(self, product_id: int, user, **fields) -> models.Product:
        self.auth.require(user, "products")
        prod = self.s.get(models.Product, product_id)
        if not prod:
            raise ValueError("Product not found")
        for k, v in fields.items():
            if k in ("sell_price", "cost_price"):
                v = q(v)
            if k in ("name", "sku") and isinstance(v, str):
                v = v.strip()
            setattr(prod, k, v)
        self.s.flush()
        enqueue_obj(self.s, "products", prod)
        return prod

    def set_active(self, product_id: int, active: bool, user) -> None:
        self.auth.require(user, "products")
        prod = self.s.get(models.Product, product_id)
        if prod:
            prod.is_active = active
            self.s.flush()

    def search(self, query: str, limit: int = 50) -> list[models.Product]:
        query = query.strip()
        qy = self.s.query(models.Product).filter_by(is_active=True)
        if query:
            like = f"%{query}%"
            qy = qy.filter(or_(models.Product.name.ilike(like),
                               models.Product.sku.ilike(like),
                               models.Product.barcode == query))
        return qy.order_by(models.Product.name).limit(limit).all()

    def find_by_barcode(self, barcode: str) -> models.Product | None:
        return (self.s.query(models.Product)
                .filter_by(barcode=barcode.strip(), is_active=True).first())

    def tax_rate_of(self, product: models.Product) -> Decimal:
        if product.tax_rate_id:
            tr = self.s.get(models.TaxRate, product.tax_rate_id)
            if tr:
                return d(tr.rate_percent)
        tr = self.s.query(models.TaxRate).filter_by(is_default=True).first()
        return d(tr.rate_percent) if tr else Decimal("0")

    # -- variants & modifiers ---------------------------------------------------------
    def add_variant(self, product_id: int, name: str, price_delta: Decimal,
                    user) -> models.ProductVariant:
        self.auth.require(user, "products")
        v = models.ProductVariant(product_id=product_id, name=name,
                                   price_delta=q(price_delta))
        self.s.add(v)
        self.s.flush()
        return v

    def create_modifier(self, name: str, price: Decimal, user) -> models.Modifier:
        self.auth.require(user, "products")
        m = models.Modifier(name=name, price=q(price))
        self.s.add(m)
        self.s.flush()
        return m

    def attach_modifier(self, product_id: int, modifier_id: int, user) -> None:
        self.auth.require(user, "products")
        if not self.s.query(models.ProductModifier).filter_by(
                product_id=product_id, modifier_id=modifier_id).first():
            self.s.add(models.ProductModifier(product_id=product_id,
                                              modifier_id=modifier_id))
            self.s.flush()

    # -- bulk & CSV ---------------------------------------------------------------------
    def bulk_price_update(self, category_id: int | None, percent: Decimal,
                          user) -> int:
        """Adjust sell prices by percent (e.g. 10 = +10%). Returns rows updated."""
        self.auth.require(user, "products")
        qy = self.s.query(models.Product).filter_by(is_active=True)
        if category_id:
            qy = qy.filter_by(category_id=category_id)
        factor = Decimal("1") + d(percent) / 100
        n = 0
        for p in qy:
            p.sell_price = q(p.sell_price * factor)
            n += 1
        self.s.flush()
        return n

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["sku", "barcode", "name", "name_ur", "category", "cost_price",
                    "sell_price", "tax_rate_id", "track_stock", "min_stock", "is_active"])
        for p in self.s.query(models.Product).order_by(models.Product.sku):
            cat = p.category.name if p.category else ""
            w.writerow([p.sku, p.barcode or "", p.name, p.name_ur, cat,
                        p.cost_price, p.sell_price, p.tax_rate_id or "",
                        int(p.track_stock), p.min_stock, int(p.is_active)])
        return buf.getvalue()

    def import_csv(self, csv_text: str, user) -> dict:
        """Upsert by SKU. Returns {created, updated, errors}."""
        self.auth.require(user, "products")
        created = updated = 0
        errors = []
        reader = csv.DictReader(io.StringIO(csv_text))
        for i, row in enumerate(reader, start=2):
            try:
                sku = (row.get("sku") or "").strip()
                if not sku:
                    raise ValueError("missing sku")
                existing = self.s.query(models.Product).filter_by(sku=sku).first()
                kwargs = dict(
                    name=(row.get("name") or sku).strip(),
                    sell_price=d(row.get("sell_price") or 0),
                    cost_price=d(row.get("cost_price") or 0),
                    barcode=(row.get("barcode") or "").strip() or None,
                    name_ur=(row.get("name_ur") or "").strip(),
                    track_stock=(row.get("track_stock") or "1") == "1",
                    min_stock=d(row.get("min_stock") or 0),
                )
                if existing:
                    for k, v in kwargs.items():
                        setattr(existing, k, v)
                    updated += 1
                    enqueue_obj(self.s, "products", existing)
                else:
                    new_prod = models.Product(sku=sku, **kwargs)
                    self.s.add(new_prod)
                    self.s.flush()
                    enqueue_obj(self.s, "products", new_prod)
                    created += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"row {i}: {e}")
        self.s.flush()
        return {"created": created, "updated": updated, "errors": errors}

    def _default_tax_id(self) -> int | None:
        tr = self.s.query(models.TaxRate).filter_by(is_default=True).first()
        return tr.id if tr else None