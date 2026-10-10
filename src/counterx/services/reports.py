"""Reports computed from real stored records. Totals always reconcile."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
from ..utils.money import d, q


class ReportService:
    def __init__(self, session: Session):
        self.s = session

    def _sales_q(self, date_from: str, date_to: str):
        return (self.s.query(models.Sale)
                .filter(models.Sale.business_day >= date_from,
                        models.Sale.business_day <= date_to,
                        models.Sale.status == "completed"))

    def sales_summary(self, date_from: str, date_to: str) -> dict:
        sales = self._sales_q(date_from, date_to).all()
        gross = discount = tax = net = Decimal("0")
        by_type: dict[str, dict] = {}
        by_method: dict[str, Decimal] = {}
        for sale in sales:
            gross += sale.subtotal
            discount += sale.discount_total
            tax += sale.tax_total
            net += sale.grand_total
            t = by_type.setdefault(sale.sale_type, {"count": 0, "total": Decimal("0")})
            t["count"] += 1
            t["total"] = q(t["total"] + sale.grand_total)
            for p in sale.payments:
                by_method[p.method] = q(by_method.get(p.method, Decimal("0")) + p.amount)
        refunds = self.s.query(func.coalesce(func.sum(models.Refund.amount), 0)).join(
            models.Sale, models.Refund.sale_id == models.Sale.id).filter(
            models.Sale.business_day >= date_from, models.Sale.business_day <= date_to).scalar() or 0
        voided = (self.s.query(func.count(models.Sale.id))
                  .filter(models.Sale.business_day >= date_from,
                          models.Sale.business_day <= date_to,
                          models.Sale.status == "voided").scalar() or 0)
        return {
            "from": date_from, "to": date_to,
            "transactions": len(sales),
            "gross": q(gross), "discount": q(discount), "tax": q(tax), "net": q(net),
            "refunds": q(refunds), "voided_count": voided,
            "by_type": {k: {"count": v["count"], "total": q(v["total"])}
                        for k, v in by_type.items()},
            "by_method": {k: q(v) for k, v in by_method.items()},
        }

    def daily_sales(self, day: str | None = None) -> dict:
        day = day or datetime.now().strftime("%Y-%m-%d")
        return self.sales_summary(day, day)

    def product_wise(self, date_from: str, date_to: str, limit: int = 500) -> list[dict]:
        rows = (self.s.query(
                    models.SaleItem.name_snapshot,
                    func.sum(models.SaleItem.qty).label("qty"),
                    func.sum(models.SaleItem.line_total).label("total"))
                .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
                .filter(models.Sale.business_day >= date_from,
                        models.Sale.business_day <= date_to,
                        models.Sale.status == "completed")
                .group_by(models.SaleItem.name_snapshot)
                .order_by(func.sum(models.SaleItem.line_total).desc())
                .limit(limit).all())
        return [{"name": r[0], "qty": q(r[1] or 0), "total": q(r[2] or 0)} for r in rows]

    def category_wise(self, date_from: str, date_to: str) -> list[dict]:
        rows = (self.s.query(
                    models.Category.name,
                    func.sum(models.SaleItem.line_total).label("total"),
                    func.sum(models.SaleItem.qty).label("qty"))
                .join(models.SaleItem, models.SaleItem.sale_id == models.Sale.id)
                .join(models.Sale, models.Sale.id == models.SaleItem.sale_id)
                .outerjoin(models.Product, models.Product.id == models.SaleItem.product_id)
                .outerjoin(models.Category, models.Category.id == models.Product.category_id)
                .filter(models.Sale.business_day >= date_from,
                        models.Sale.business_day <= date_to,
                        models.Sale.status == "completed")
                .group_by(models.Category.name)
                .order_by(func.sum(models.SaleItem.line_total).desc()).all())
        return [{"category": r[0] or "Uncategorized", "total": q(r[1] or 0),
                 "qty": q(r[2] or 0)} for r in rows]

    def cashier_performance(self, date_from: str, date_to: str) -> list[dict]:
        rows = (self.s.query(
                    models.User.username, models.User.full_name,
                    func.count(models.Sale.id).label("count"),
                    func.sum(models.Sale.grand_total).label("total"))
                .join(models.Sale, models.Sale.user_id == models.User.id)
                .filter(models.Sale.business_day >= date_from,
                        models.Sale.business_day <= date_to,
                        models.Sale.status == "completed")
                .group_by(models.User.id).all())
        return [{"username": r[0], "name": r[1] or r[0], "transactions": r[2],
                 "total": q(r[3] or 0)} for r in rows]

    def discounts(self, date_from: str, date_to: str) -> dict:
        rows = self._sales_q(date_from, date_to).all()
        total = q(sum((s.discount_total for s in rows), Decimal("0")))
        return {"count": sum(1 for s in rows if s.discount_total > 0),
                "total": total}

    def tax_summary(self, date_from: str, date_to: str) -> dict:
        rows = self._sales_q(date_from, date_to).all()
        taxable = q(sum((s.subtotal - s.discount_total for s in rows), Decimal("0")))
        tax = q(sum((s.tax_total for s in rows), Decimal("0")))
        return {"taxable_amount": taxable, "tax_total": tax}

    def profit_estimate(self, date_from: str, date_to: str) -> dict:
        """Estimated gross profit = net sales - cost of goods sold (uses cost_price
        snapshot at sale time is not stored, so this uses current cost_price and is
        clearly labelled an estimate)."""
        rows = self._sales_q(date_from, date_to).all()
        net = Decimal("0")
        cogs = Decimal("0")
        for sale in rows:
            net += sale.grand_total
            for item in sale.items:
                prod = self.s.get(models.Product, item.product_id) if item.product_id else None
                cost = prod.cost_price if prod and prod.cost_price else Decimal("0")
                cogs += d(item.qty) * d(cost)
        return {"net_sales": q(net), "cogs_estimate": q(cogs),
                "gross_profit_estimate": q(net - cogs),
                "note": "Estimate: uses current cost prices; excludes expenses, waste and overheads."}

    def cash_discrepancies(self, limit: int = 100) -> list[dict]:
        shifts = (self.s.query(models.Shift).filter_by(status="closed")
                  .order_by(models.Shift.closed_at.desc()).limit(limit).all())
        return [{"id": sh.id, "business_day": sh.business_day,
                 "expected": sh.expected_cash, "counted": sh.closing_cash_counted,
                 "variance": sh.variance} for sh in shifts if sh.variance]

    def audit_log(self, limit: int = 500) -> list[models.AuditLog]:
        return (self.s.query(models.AuditLog)
                .order_by(models.AuditLog.created_at.desc(),
                          models.AuditLog.id.desc()).limit(limit).all())
