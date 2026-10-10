"""Dashboard screen: today's KPIs, breakdowns, low stock, shift, top products."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from counterx.utils.money import fmt, q

from ..base import BaseScreen
from ..theme import set_class


def _kpi_card(title: str) -> tuple[QFrame, QLabel]:
    card = QFrame()
    set_class(card, "card")
    layout = QVBoxLayout(card)
    layout.setSpacing(4)
    t = QLabel(title)
    set_class(t, "muted")
    v = QLabel(fmt(0))
    set_class(v, "kpi")
    layout.addWidget(t)
    layout.addWidget(v)
    return card, v


def _panel(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    set_class(card, "card")
    layout = QVBoxLayout(card)
    layout.setSpacing(6)
    t = QLabel(title)
    set_class(t, "h2")
    layout.addWidget(t)
    return card, layout


class DashboardScreen(BaseScreen):
    nav_title = "Dashboard"
    nav_permission = None
    nav_order = 10

    # ------------------------------------------------------------------ UI ---
    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Dashboard")
        set_class(title, "h1")
        top.addWidget(title)
        top.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setSpacing(10)

        # ---- KPI row ----
        kpi_titles = ["Today's Net Sales", "Transactions", "Gross",
                      "Discount", "Tax"]
        self._kpi_vals: list[QLabel] = []
        for col, title_text in enumerate(kpi_titles):
            card, val = _kpi_card(title_text)
            grid.addWidget(card, 0, col)
            self._kpi_vals.append(val)
        (self._net_val, self._tx_val, self._gross_val,
         self._disc_val, self._tax_val) = self._kpi_vals

        # ---- panels ----
        pay_card, self._pay_layout = _panel("Payment Breakdown")
        grid.addWidget(pay_card, 1, 0, 1, 2)
        type_card, self._type_layout = _panel("Order Types")
        grid.addWidget(type_card, 1, 2, 1, 2)
        shift_card, self._shift_layout = _panel("Current Shift")
        grid.addWidget(shift_card, 1, 4)

        low_card, self._low_layout = _panel("Low Stock")
        grid.addWidget(low_card, 2, 0, 1, 3)
        top_card, self._top_layout = _panel("Top Products (Today)")
        grid.addWidget(top_card, 2, 3, 1, 2)

        grid.setRowStretch(3, 1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def on_show(self) -> None:
        self.refresh()

    # -------------------------------------------------------------- refresh ---
    def refresh(self) -> None:
        day = datetime.now().strftime("%Y-%m-%d")

        def _do():
            with self.db() as s:
                svc = self.svc(s)
                report = svc.reports.daily_sales(day)
                low = [{"name": r["product"].name,
                        "level": q(r["level"]), "min": q(r["min"])}
                       for r in svc.inventory.low_stock()[:8]]
                shift = svc.shifts.current_shift()
                shift_info = None
                if shift is not None:
                    shift_info = {
                        "id": shift.id,
                        "business_day": shift.business_day,
                        "opened_at": (shift.opened_at.strftime("%Y-%m-%d %H:%M")
                                      if shift.opened_at else ""),
                        "expected_cash": svc.shifts.expected_cash(shift.id),
                    }
                top = [{"name": r["name"], "qty": r["qty"], "total": r["total"]}
                       for r in svc.reports.product_wise(day, day, limit=5)]
                return report, low, shift_info, top

        res = self.safe(_do)
        if res is None:
            return
        report, low, shift_info, top = res

        self._net_val.setText(fmt(report["net"]))
        self._tx_val.setText(str(report["transactions"]))
        self._gross_val.setText(fmt(report["gross"]))
        self._disc_val.setText(fmt(report["discount"]))
        self._tax_val.setText(fmt(report["tax"]))

        self._fill_breakdown(self._pay_layout, report["by_method"])
        self._fill_type_breakdown(self._type_layout, report["by_type"])
        self._fill_shift(self._shift_layout, shift_info)
        self._fill_low_stock(self._low_layout, low)
        self._fill_top(self._top_layout, top)

    # --------------------------------------------------------------- fillers --
    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count() > 1:  # keep the title label at index 0
            child = layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()

    def _fill_breakdown(self, layout: QVBoxLayout, by_method: dict) -> None:
        self._clear(layout)
        if not by_method:
            lbl = QLabel("No data yet")
            set_class(lbl, "muted")
            layout.addWidget(lbl)
            return
        for method, amount in sorted(by_method.items()):
            row = QHBoxLayout()
            name = QLabel(method.replace("_", " ").title())
            val = QLabel(fmt(amount))
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(val)
            wrap = QWidget()
            wrap.setLayout(row)
            layout.addWidget(wrap)

    def _fill_type_breakdown(self, layout: QVBoxLayout, by_type: dict) -> None:
        self._clear(layout)
        if not by_type:
            lbl = QLabel("No data yet")
            set_class(lbl, "muted")
            layout.addWidget(lbl)
            return
        for stype, info in sorted(by_type.items()):
            row = QHBoxLayout()
            name = QLabel(f"{stype.replace('_', ' ').title()} ({info['count']})")
            val = QLabel(fmt(info["total"]))
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(val)
            wrap = QWidget()
            wrap.setLayout(row)
            layout.addWidget(wrap)

    def _fill_shift(self, layout: QVBoxLayout, shift_info: dict | None) -> None:
        self._clear(layout)
        if shift_info is None:
            lbl = QLabel("No shift open")
            set_class(lbl, "muted")
            layout.addWidget(lbl)
            return
        for text in (f"Shift #{shift_info['id']} — {shift_info['business_day']}",
                     f"Opened: {shift_info['opened_at']}",
                     f"Expected cash: {fmt(shift_info['expected_cash'])}"):
            layout.addWidget(QLabel(text))

    def _fill_low_stock(self, layout: QVBoxLayout, low: list[dict]) -> None:
        self._clear(layout)
        if not low:
            lbl = QLabel("All stocked up")
            set_class(lbl, "muted")
            layout.addWidget(lbl)
            return
        for r in low:
            lbl = QLabel(f"{r['name']} — {r['level']} / {r['min']}")
            layout.addWidget(lbl)

    def _fill_top(self, layout: QVBoxLayout, top: list[dict]) -> None:
        self._clear(layout)
        if not top:
            lbl = QLabel("No data yet")
            set_class(lbl, "muted")
            layout.addWidget(lbl)
            return
        for i, r in enumerate(top, 1):
            lbl = QLabel(f"{i}. {r['name']} — {r['qty']} sold ({fmt(r['total'])})")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
