"""Reports & Analytics screen: flexible reports with CSV export and print."""
from __future__ import annotations

import csv
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ... import models
from ...utils.money import d, fmt, q
from ..base import BaseScreen, get_setting
from ..dialogs import TextPreviewDialog
from ..theme import set_class

REPORT_SALES_SUMMARY = "sales_summary"
REPORT_PRODUCT_WISE = "product_wise"
REPORT_CATEGORY_WISE = "category_wise"
REPORT_CASHIER = "cashier_performance"
REPORT_DISCOUNTS = "discounts"
REPORT_TAX = "tax_summary"
REPORT_PROFIT = "profit_estimate"
REPORT_DISCREPANCIES = "cash_discrepancies"
REPORT_AUDIT = "audit_log"

REPORTS = [
    ("Sales Summary", REPORT_SALES_SUMMARY),
    ("Product-wise Sales", REPORT_PRODUCT_WISE),
    ("Category-wise Sales", REPORT_CATEGORY_WISE),
    ("Cashier Performance", REPORT_CASHIER),
    ("Discounts", REPORT_DISCOUNTS),
    ("Tax Summary", REPORT_TAX),
    ("Profit Estimate", REPORT_PROFIT),
    ("Cash Discrepancies", REPORT_DISCREPANCIES),
    ("Audit Log", REPORT_AUDIT),
]


def _qty_str(value) -> str:
    s = format(d(value), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def _money_or_dash(value) -> str:
    return fmt(q(value)) if value is not None else "—"


def _variance_item(text: str, value) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    try:
        v = d(value)
        if v < 0:
            item.setForeground(QColor("#D64545"))
        elif v > 0:
            item.setForeground(QColor("#1E9E6A"))
    except Exception:  # noqa: BLE001
        pass
    return item


def _fill_table(table: QTableWidget, headers: list[str],
                rows: list[list[QTableWidgetItem | str]]) -> None:
    table.clear()
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        table.insertRow(r)
        for c, val in enumerate(row):
            item = val if isinstance(val, QTableWidgetItem) else QTableWidgetItem(str(val))
            if not isinstance(val, QTableWidgetItem):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


def _report_text(title: str, kpis: list[tuple[str, str]],
                 headers: list[str], rows: list[list[str]]) -> str:
    lines = [title, "=" * len(title), ""]
    for name, val in kpis:
        lines.append(f"{name}: {val}")
    if kpis:
        lines.append("")
    if headers:
        lines.append(" | ".join(headers))
        lines.append("-" * 60)
        for row in rows:
            lines.append(" | ".join(str(c) for c in row))
    return "\n".join(lines)


class ReportsScreen(BaseScreen):
    nav_title = "Reports & Analytics"
    nav_permission = "reports"
    nav_order = 140

    def build_ui(self) -> None:
        # self._current keeps plain values for CSV export / print:
        # {"title", "kpis": [(name, value_str)], "headers": [...],
        #  "rows": [[str, ...]], "note": str|None}
        self._current: dict | None = None

        root = QVBoxLayout(self)
        title = QLabel("Reports & Analytics")
        set_class(title, "h1")
        root.addWidget(title)

        # -- controls --
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("From:"))
        self.from_edit = QDateEdit()
        self.from_edit.setDisplayFormat("dd-MM-yyyy")
        self.from_edit.setCalendarPopup(True)
        ctrl_row.addWidget(self.from_edit)
        ctrl_row.addWidget(QLabel("To:"))
        self.to_edit = QDateEdit()
        self.to_edit.setDisplayFormat("dd-MM-yyyy")
        self.to_edit.setCalendarPopup(True)
        ctrl_row.addWidget(self.to_edit)
        ctrl_row.addWidget(QLabel("Report:"))
        self.report_combo = QComboBox()
        for label, _key in REPORTS:
            self.report_combo.addItem(label)
        ctrl_row.addWidget(self.report_combo)
        self.run_btn = QPushButton("Run")
        set_class(self.run_btn, "primary")
        self.run_btn.clicked.connect(self._run_report)
        ctrl_row.addWidget(self.run_btn)
        self.csv_btn = QPushButton("Export CSV")
        self.csv_btn.clicked.connect(self._export_csv)
        self.print_btn = QPushButton("Print")
        self.print_btn.clicked.connect(self._print_report)
        ctrl_row.addWidget(self.csv_btn)
        ctrl_row.addWidget(self.print_btn)
        ctrl_row.addStretch(1)
        root.addLayout(ctrl_row)
        self.gate(self.run_btn, "reports")
        self.gate(self.csv_btn, "reports")
        self.gate(self.print_btn, "reports")

        # defaults: first of month -> today
        today = date.today()
        self.from_edit.setDate(QDate(today.year, today.month, 1))
        self.to_edit.setDate(QDate(today.year, today.month, today.day))

        # -- results --
        self.results_area = QVBoxLayout()
        root.addLayout(self.results_area)
        root.addStretch(1)

        self._update_buttons()

    def on_show(self) -> None:
        self._run_report()

    # -- helpers -------------------------------------------------------------------
    def _update_buttons(self) -> None:
        has = self._current is not None and bool(self._current.get("rows")
                                                 or self._current.get("kpis"))
        self.csv_btn.setEnabled(has)
        self.print_btn.setEnabled(has)

    def _clear_results(self) -> None:
        while self.results_area.count():
            child = self.results_area.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _kpi_row(self, kpis: list[tuple[str, str]]) -> QFrame | None:
        if not kpis:
            return None
        holder = QFrame()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        for name, val in kpis:
            frame = QFrame()
            set_class(frame, "card")
            flay = QVBoxLayout(frame)
            name_lbl = QLabel(name)
            set_class(name_lbl, "muted")
            val_lbl = QLabel(val)
            set_class(val_lbl, "kpi")
            flay.addWidget(name_lbl)
            flay.addWidget(val_lbl)
            lay.addWidget(frame)
        return holder

    def _show_result(self, title: str, kpis: list[tuple[str, str]],
                     headers: list[str], rows: list,
                     note: str | None = None) -> None:
        self._clear_results()
        h = QLabel(title)
        set_class(h, "h2")
        self.results_area.addWidget(h)
        kpi_widget = self._kpi_row(kpis)
        if kpi_widget is not None:
            self.results_area.addWidget(kpi_widget)
        if note:
            note_lbl = QLabel(note)
            set_class(note_lbl, "muted")
            note_lbl.setWordWrap(True)
            self.results_area.addWidget(note_lbl)
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        _fill_table(table, headers, rows)
        self.results_area.addWidget(table)
        # plain strings for CSV / print
        plain_rows = []
        for r in rows:
            plain = []
            for c in r:
                plain.append(c.text() if isinstance(c, QTableWidgetItem) else str(c))
            plain_rows.append(plain)
        self._current = {"title": title, "kpis": kpis, "headers": headers,
                         "rows": plain_rows, "note": note}
        self._update_buttons()

    def _dates(self) -> tuple[str, str]:
        return (self.from_edit.date().toString("yyyy-MM-dd"),
                self.to_edit.date().toString("yyyy-MM-dd"))

    # -- run -----------------------------------------------------------------------
    def _run_report(self) -> None:
        key = REPORTS[self.report_combo.currentIndex()][1]
        date_from, date_to = self._dates()
        if date_from > date_to:
            self.warn("The From date must not be after the To date.")
            return
        handler = {
            REPORT_SALES_SUMMARY: self._r_sales_summary,
            REPORT_PRODUCT_WISE: self._r_product_wise,
            REPORT_CATEGORY_WISE: self._r_category_wise,
            REPORT_CASHIER: self._r_cashier,
            REPORT_DISCOUNTS: self._r_discounts,
            REPORT_TAX: self._r_tax,
            REPORT_PROFIT: self._r_profit,
            REPORT_DISCREPANCIES: self._r_discrepancies,
            REPORT_AUDIT: self._r_audit,
        }[key]
        self.safe(handler, date_from, date_to)

    def _report_range_title(self, name: str, date_from: str, date_to: str) -> str:
        return f"{name} ({date_from} to {date_to})"

    # -- individual reports ----------------------------------------------------------
    def _r_sales_summary(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            r = self.svc(s).reports.sales_summary(date_from, date_to)
            kpis = [("Transactions", str(r["transactions"])),
                    ("Gross", self.money(r["gross"])),
                    ("Discount", self.money(r["discount"])),
                    ("Tax", self.money(r["tax"])),
                    ("Net", self.money(r["net"])),
                    ("Refunds", self.money(r["refunds"])),
                    ("Voided", str(r["voided_count"]))]
            rows = [[t, v["count"], self.money(v["total"])]
                    for t, v in sorted(r["by_type"].items())]
            mrows = [[m, self.money(total)]
                     for m, total in sorted(r["by_method"].items())]
            title = self._report_range_title("Sales Summary", date_from, date_to)
        self._clear_results()
        h = QLabel(title)
        set_class(h, "h2")
        self.results_area.addWidget(h)
        self.results_area.addWidget(self._kpi_row(kpis))
        t_lbl = QLabel("Sales by type")
        set_class(t_lbl, "h2")
        self.results_area.addWidget(t_lbl)
        t1 = QTableWidget()
        t1.setAlternatingRowColors(True)
        _fill_table(t1, ["Sale type", "Count", "Total"], rows)
        self.results_area.addWidget(t1)
        m_lbl = QLabel("Payments by method")
        set_class(m_lbl, "h2")
        self.results_area.addWidget(m_lbl)
        t2 = QTableWidget()
        t2.setAlternatingRowColors(True)
        _fill_table(t2, ["Method", "Total"], mrows)
        self.results_area.addWidget(t2)
        combined = [["BY TYPE"] + []] + [[t, str(c), tot] for t, c, tot in rows] \
            + [["BY METHOD"] + []] + [[m, "", tot] for m, tot in mrows]
        self._current = {"title": title, "kpis": kpis,
                         "headers": ["Section", "Detail", "Value"],
                         "rows": combined, "note": None}
        self._update_buttons()

    def _r_product_wise(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            rows = self.svc(s).reports.product_wise(date_from, date_to)
            table_rows = [[r["name"], _qty_str(r["qty"]), self.money(r["total"])]
                          for r in rows]
        self._show_result(
            self._report_range_title("Product-wise Sales", date_from, date_to),
            [], ["Product", "Qty", "Total"], table_rows)

    def _r_category_wise(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            rows = self.svc(s).reports.category_wise(date_from, date_to)
            table_rows = [[r["category"], _qty_str(r["qty"]), self.money(r["total"])]
                          for r in rows]
        self._show_result(
            self._report_range_title("Category-wise Sales", date_from, date_to),
            [], ["Category", "Qty", "Total"], table_rows)

    def _r_cashier(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            rows = self.svc(s).reports.cashier_performance(date_from, date_to)
            table_rows = [[f"{r['name']} ({r['username']})", str(r["transactions"]),
                           self.money(r["total"])] for r in rows]
        self._show_result(
            self._report_range_title("Cashier Performance", date_from, date_to),
            [], ["Cashier", "Transactions", "Total"], table_rows)

    def _r_discounts(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            r = self.svc(s).reports.discounts(date_from, date_to)
            kpis = [("Discounted transactions", str(r["count"])),
                    ("Total discounts", self.money(r["total"]))]
        self._show_result(
            self._report_range_title("Discounts", date_from, date_to),
            kpis, [], [])

    def _r_tax(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            r = self.svc(s).reports.tax_summary(date_from, date_to)
            kpis = [("Taxable amount", self.money(r["taxable_amount"])),
                    ("Tax total", self.money(r["tax_total"]))]
        self._show_result(
            self._report_range_title("Tax Summary", date_from, date_to),
            kpis, [], [])

    def _r_profit(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            r = self.svc(s).reports.profit_estimate(date_from, date_to)
            kpis = [("Net sales", self.money(r["net_sales"])),
                    ("COGS (estimate)", self.money(r["cogs_estimate"])),
                    ("Gross profit (estimate)",
                     self.money(r["gross_profit_estimate"]))]
            note = r["note"]
        self._show_result(
            self._report_range_title("Profit Estimate", date_from, date_to),
            kpis, [], [], note=note)

    def _r_discrepancies(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            rows = self.svc(s).reports.cash_discrepancies(100)
            table_rows = []
            for r in rows:
                var_item = _variance_item(
                    _money_or_dash(r["variance"]), r["variance"])
                table_rows.append([
                    str(r["id"]), r["business_day"],
                    _money_or_dash(r["expected"]),
                    _money_or_dash(r["counted"]),
                    var_item])
        self._show_result("Cash Discrepancies (closed shifts)", [],
                          ["Shift", "Day", "Expected", "Counted", "Variance"],
                          table_rows,
                          note="Only closed shifts with a non-zero variance are listed.")

    def _r_audit(self, date_from: str, date_to: str) -> None:
        with self.db() as s:
            logs = self.svc(s).reports.audit_log(500)
            user_ids = {l.user_id for l in logs if l.user_id}
            users = (s.query(models.User).filter(models.User.id.in_(user_ids)).all()
                     if user_ids else [])
            names = {u.id: u.username for u in users}
            table_rows = []
            for l in logs:
                details = (l.details or "")
                if len(details) > 100:
                    details = details[:97] + "..."
                table_rows.append([
                    l.created_at.strftime("%d-%m-%Y %H:%M") if l.created_at else "—",
                    names.get(l.user_id, "—") if l.user_id else "—",
                    l.action or "—", l.entity or "—", details])
        self._show_result("Audit Log (latest 500 entries)", [],
                          ["Time", "User", "Action", "Entity", "Details"],
                          table_rows)

    # -- export / print --------------------------------------------------------------
    def _export_csv(self) -> None:
        if self._current is None:
            return
        cur = self._current
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in cur["title"])
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", f"{safe_name}.csv", "CSV files (*.csv)")
        if not path:
            return

        def do() -> bool:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow([cur["title"]])
                w.writerow([])
                for name, val in cur["kpis"]:
                    w.writerow([name, val])
                if cur["kpis"]:
                    w.writerow([])
                if cur.get("note"):
                    w.writerow([cur["note"]])
                    w.writerow([])
                if cur["headers"]:
                    w.writerow(cur["headers"])
                    w.writerows(cur["rows"])
            return True

        if self.safe(do):
            self.info(f"Report exported to:\n{path}")

    def _print_report(self) -> None:
        if self._current is None:
            return
        cur = self._current

        def do() -> tuple | None:
            with self.db() as s:
                printer = get_setting(s, "receipt_printer", "")
            return (printer,)

        res = self.safe(do)
        if res is None:
            return
        printer = res[0]
        lines = [cur["title"], "=" * len(cur["title"]), ""]
        for name, val in cur["kpis"]:
            lines.append(f"{name}: {val}")
        if cur["kpis"]:
            lines.append("")
        if cur.get("note"):
            lines.append(cur["note"])
            lines.append("")
        if cur["headers"]:
            lines.append(" | ".join(cur["headers"]))
            lines.append("-" * 60)
            for row in cur["rows"]:
                lines.append(" | ".join(str(c) for c in row))
        TextPreviewDialog(self, cur["title"], "\n".join(lines), printer).exec()
