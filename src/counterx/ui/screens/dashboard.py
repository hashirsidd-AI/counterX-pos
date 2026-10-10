"""Dashboard screen: KPIs, 7-day sales chart, recent transactions, panels."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from counterx.utils.money import d, fmt, q

from ... import models
from ..base import BaseScreen
from ..theme import set_class

TEAL = "#0F9D8A"


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


class SalesBarChart(QWidget):
    """Lightweight 7-day sales bar chart (QPainter, no new dependencies)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, Decimal]] = []
        self.setMinimumHeight(170)

    def set_data(self, data: list[tuple[str, Decimal]]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._data:
            painter.drawText(10, h // 2, "No sales data yet")
            return
        max_v = max((float(v) for _, v in self._data), default=0.0)
        n = len(self._data)
        slot = w / n
        bar_w = min(44.0, slot * 0.55)
        base = h - 26
        for i, (label, value) in enumerate(self._data):
            v = float(value)
            bar_h = (base - 12) * (v / max_v) if max_v > 0 else 0
            x = slot * i + (slot - bar_w) / 2
            painter.fillRect(int(x), int(base - bar_h), int(bar_w), int(bar_h),
                             QColor(TEAL))
            painter.setPen(QColor("#697586"))
            painter.drawText(int(slot * i), base + 4, int(slot), 20,
                             Qt.AlignmentFlag.AlignHCenter, label)


class DashboardScreen(BaseScreen):
    nav_title = "Dashboard"
    nav_permission = None
    nav_order = 10

    # ------------------------------------------------------------------ UI ---
    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ---- header: business name + date/shift/user + refresh ----
        top = QHBoxLayout()
        self.business_lbl = QLabel("Dashboard")
        set_class(self.business_lbl, "h1")
        top.addWidget(self.business_lbl)
        top.addStretch(1)
        self.meta_lbl = QLabel("")
        set_class(self.meta_lbl, "muted")
        top.addWidget(self.meta_lbl)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        top.addWidget(self.btn_refresh)
        root.addLayout(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setSpacing(10)

        # ---- KPI row (6 cards) ----
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)
        kpi_titles = ["Today's Sales", "Orders", "Avg Order Value",
                      "Cash in Shift", "Low-Stock Items", "Held Orders"]
        self._kpi_vals: list[QLabel] = []
        for col, title_text in enumerate(kpi_titles):
            card, val = _kpi_card(title_text)
            kpi_grid.addWidget(card, 0, col)
            self._kpi_vals.append(val)
        (self._sales_val, self._orders_val, self._avg_val, self._cash_val,
         self._low_val, self._held_val) = self._kpi_vals
        self.body_layout.addLayout(kpi_grid)

        # ---- content row: chart + recent (left) / panels (right) ----
        content = QHBoxLayout()
        content.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        chart_card, chart_layout = _panel("Sales — Last 7 Days")
        self.chart = SalesBarChart()
        chart_layout.addWidget(self.chart)
        left_col.addWidget(chart_card)

        recent_card, recent_layout = _panel("Recent Transactions")
        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels(
            ["Time", "Invoice #", "Items", "Method", "Total"])
        self.recent_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        recent_layout.addWidget(self.recent_table)
        left_col.addWidget(recent_card, 1)
        content.addLayout(left_col, 2)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        pay_card, self._pay_layout = _panel("Payment Breakdown")
        right_col.addWidget(pay_card)
        type_card, self._type_layout = _panel("Order Types")
        right_col.addWidget(type_card)
        shift_card, self._shift_layout = _panel("Current Shift")
        right_col.addWidget(shift_card)
        low_card, self._low_layout = _panel("Low Stock")
        right_col.addWidget(low_card)
        top_card, self._top_layout = _panel("Top Products (Today)")
        right_col.addWidget(top_card)
        right_col.addStretch(1)
        content.addLayout(right_col, 1)

        self.body_layout.addLayout(content, 1)

        # ---- empty state (shown when no completed sale exists yet) ----
        self.empty_card = QFrame()
        set_class(self.empty_card, "card")
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(8)
        empty_title = QLabel("No sales yet")
        set_class(empty_title, "h1")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub = QLabel("Your sales will appear here.")
        set_class(empty_sub, "muted")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_btn = QPushButton("Create Your First Sale")
        set_class(self.empty_btn, "primary")
        self.empty_btn.clicked.connect(lambda: self._goto("New Sale"))
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_sub)
        empty_layout.addWidget(self.empty_btn,
                               alignment=Qt.AlignmentFlag.AlignCenter)
        self.body_layout.addWidget(self.empty_card)
        self.empty_card.setVisible(False)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def on_show(self) -> None:
        self.refresh()

    # ------------------------------------------------------------ navigation --
    def _goto(self, nav_title: str) -> None:
        mw = self.window()
        if mw is None:
            return
        screens = getattr(mw, "screens", {})
        screen = screens.get(nav_title)
        idx = getattr(screen, "_nav_index", None) if screen else None
        if idx is not None and hasattr(mw, "show_screen"):
            mw.show_screen(idx)

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
                cash_in_shift = Decimal("0")
                if shift is not None:
                    cash_in_shift = svc.shifts.expected_cash(shift.id)
                    shift_info = {
                        "id": shift.id,
                        "business_day": shift.business_day,
                        "opened_at": (shift.opened_at.strftime("%Y-%m-%d %H:%M")
                                      if shift.opened_at else ""),
                        "expected_cash": cash_in_shift,
                    }
                top = [{"name": r["name"], "qty": r["qty"], "total": r["total"]}
                       for r in svc.reports.product_wise(day, day, limit=5)]
                held = svc.sales.held_sales()
                # 7-day sales (net, completed only)
                week = []
                for back in range(6, -1, -1):
                    dday = (datetime.now() - timedelta(days=back)).strftime("%Y-%m-%d")
                    rep = svc.reports.daily_sales(dday)
                    label = (datetime.now() - timedelta(days=back)).strftime("%a")
                    week.append((label, rep["net"]))
                # recent transactions: last 10 completed sales
                recent_q = (s.query(models.Sale)
                            .filter_by(status="completed")
                            .order_by(models.Sale.created_at.desc(),
                                      models.Sale.id.desc()).limit(10).all())
                recent = []
                for sale in recent_q:
                    method = sale.payments[0].method.replace("_", " ").title() \
                        if sale.payments else "—"
                    recent.append({
                        "time": (sale.created_at.strftime("%H:%M")
                                 if sale.created_at else ""),
                        "invoice": f"#{sale.invoice_no}",
                        "items": str(len(sale.items)),
                        "method": method,
                        "total": fmt(sale.grand_total),
                    })
                ever = s.query(models.Sale).filter_by(status="completed").count()
                business_name = self.ctx.business_name or "Dashboard"
                return (report, low, shift_info, cash_in_shift, top,
                        len(held), week, recent, ever, business_name)

        res = self.safe(_do)
        if res is None:
            return
        (report, low, shift_info, cash_in_shift, top, held_count,
         week, recent, ever, business_name) = res

        # header
        self.business_lbl.setText(business_name)
        shift_txt = (f"Shift #{shift_info['id']} OPEN" if shift_info
                     else "No shift open")
        self.meta_lbl.setText(
            f"{datetime.now():%d %b %Y}  •  {shift_txt}  •  {self.ctx.username}")

        # KPIs
        self._sales_val.setText(fmt(report["net"]))
        self._orders_val.setText(str(report["transactions"]))
        avg = (q(report["net"] / report["transactions"])
               if report["transactions"] else Decimal("0"))
        self._avg_val.setText(fmt(avg))
        self._cash_val.setText(fmt(cash_in_shift))
        self._low_val.setText(str(len(low)))
        self._held_val.setText(str(held_count))

        # chart + recent
        self.chart.set_data(week)
        self.recent_table.setRowCount(0)
        for r in recent:
            row = self.recent_table.rowCount()
            self.recent_table.insertRow(row)
            for c, key in enumerate(("time", "invoice", "items", "method",
                                     "total")):
                item = QTableWidgetItem(r[key])
                if c >= 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                self.recent_table.setItem(row, c, item)
        self.recent_table.resizeColumnsToContents()

        # panels
        self._fill_breakdown(self._pay_layout, report["by_method"])
        self._fill_type_breakdown(self._type_layout, report["by_type"])
        self._fill_shift(self._shift_layout, shift_info)
        self._fill_low_stock(self._low_layout, low)
        self._fill_top(self._top_layout, top)

        # empty state
        self.empty_card.setVisible(ever == 0)

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
