"""Receipt / KOT / report text builders (fixed-width, thermal-printer friendly).

These produce the printable text. Sending bytes to a physical printer is
platform-specific and is wired in the UI layer (Windows: win32print).
If printing fails, the saved transaction is untouched and can be reprinted.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .. import models
from ..config import COMPANY_NAME, COMPANY_PHONES
from ..utils.money import fmt, q

WIDTH = 42


def _line(char: str = "-") -> str:
    return char * WIDTH


def _row(left: str, right: str) -> str:
    space = WIDTH - len(left) - len(right)
    if space < 1:
        return left + " " + right
    return left + " " * space + right


def _center(text: str) -> str:
    return text.center(WIDTH)


class PrintService:
    def __init__(self, session: Session):
        self.s = session

    def _setting(self, key: str, default: str = "") -> str:
        row = self.s.query(models.Setting).filter_by(key=key).first()
        return row.value if row else default

    def _header(self) -> list[str]:
        out = [_center(self._setting("business_name", COMPANY_NAME) or COMPANY_NAME)]
        for k in ("business_address", "business_city", "business_phone"):
            v = self._setting(k)
            if v:
                out.append(_center(v))
        out.append(_line())
        return out

    def _footer(self) -> list[str]:
        out = [_line(), _center(self._setting("receipt_footer", "Thank you!"))]
        out.append(_center(f"{COMPANY_NAME}: {', '.join(COMPANY_PHONES)}"))
        return out

    def receipt(self, sale_id: int) -> str:
        sale = self.s.get(models.Sale, sale_id)
        if not sale:
            raise ValueError("Sale not found")
        out = self._header()
        out.append(_row(f"Invoice: #{sale.invoice_no}", f"Token: {sale.token_no}"))
        out.append(_row(f"Date: {sale.created_at:%d-%m-%Y %H:%M}", f"Type: {sale.sale_type}"))
        if sale.table_no:
            out.append(_row(f"Table: {sale.table_no}", f"Waiter: {sale.waiter}"))
        out.append(_line())
        for item in sale.items:
            name = item.name_snapshot[:WIDTH]
            out.append(name)
            qty_price = f"{item.qty} x {fmt(item.unit_price)}"
            out.append(_row("  " + qty_price, fmt(item.line_total)))
            for m in self.s.query(models.SaleItemModifier).filter_by(sale_item_id=item.id):
                out.append(_row(f"   + {m.name_snapshot}", fmt(m.price)))
        out.append(_line("="))
        out.append(_row("Subtotal:", fmt(sale.subtotal)))
        if sale.discount_total:
            out.append(_row("Discount:", fmt(sale.discount_total)))
        if sale.tax_total:
            out.append(_row("Tax:", fmt(sale.tax_total)))
        if sale.service_charge:
            out.append(_row("Service charge:", fmt(sale.service_charge)))
        if sale.delivery_charge:
            out.append(_row("Delivery:", fmt(sale.delivery_charge)))
        out.append(_row("TOTAL:", fmt(sale.grand_total)))
        out.append(_line("="))
        for p in sale.payments:
            out.append(_row(f"Paid ({p.method}):", fmt(p.amount)))
            if p.method == "cash" and p.received:
                out.append(_row("Cash received:", fmt(p.received)))
            if p.change_due:
                out.append(_row("Change:", fmt(p.change_due)))
        out.extend(self._footer())
        return "\n".join(out)

    def kot(self, sale_id: int) -> str:
        """Kitchen Order Ticket."""
        sale = self.s.get(models.Sale, sale_id)
        if not sale:
            raise ValueError("Sale not found")
        out = [_center("** KITCHEN ORDER **"),
               _row(f"Token: {sale.token_no}", f"Inv: #{sale.invoice_no}"),
               _row(f"Type: {sale.sale_type}", f"{sale.created_at:%H:%M}")]
        if sale.table_no:
            out.append(_row(f"Table: {sale.table_no}", f"Waiter: {sale.waiter}"))
        out.append(_line("="))
        for item in sale.items:
            out.append(f"{q(item.qty)} x {item.name_snapshot[:WIDTH - 6]}")
        out.append(_line("="))
        if sale.notes:
            out.append(f"NOTE: {sale.notes}")
        return "\n".join(out)

    def shift_report(self, shift_id: int, summary: dict) -> str:
        sh = summary["shift"]
        out = [_center("SHIFT REPORT"), _center(COMPANY_NAME), _line(),
               _row(f"Business day: {sh.business_day}", ""),
               _row(f"Opened: {sh.opened_at:%d-%m-%Y %H:%M}", "")]
        if sh.closed_at:
            out.append(_row(f"Closed: {sh.closed_at:%d-%m-%Y %H:%M}", ""))
        out.append(_line("="))
        out.append(_row("Transactions:", str(summary["sales_count"])))
        out.append(_row("Gross:", fmt(summary["gross"])))
        out.append(_row("Discount:", fmt(summary["discount"])))
        out.append(_row("Tax:", fmt(summary["tax"])))
        out.append(_row("NET:", fmt(summary["net"])))
        out.append(_line())
        out.append("BY ORDER TYPE:")
        for t, v in summary["by_type"].items():
            out.append(_row(f"  {t} x{v['count']}", fmt(v["total"])))
        out.append("BY PAYMENT:")
        for m, v in summary["by_method"].items():
            out.append(_row(f"  {m}", fmt(v)))
        out.append(_line("="))
        out.append(_row("Expected cash:", fmt(summary["expected_cash"])))
        if sh.closing_cash_counted is not None:
            out.append(_row("Counted cash:", fmt(sh.closing_cash_counted)))
            out.append(_row("Variance:", fmt(sh.variance or Decimal("0"))))
        return "\n".join(out)
