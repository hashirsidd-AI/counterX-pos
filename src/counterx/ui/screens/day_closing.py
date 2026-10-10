"""Day Closing screen: review a business day's shifts, close them, print reports."""
from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ... import models
from ...utils.money import q
from ..base import BaseScreen, get_setting
from ..dialogs import CloseShiftDialog, TextPreviewDialog
from ..theme import set_class


def _fill_table(table: QTableWidget, headers: list[str], rows: list[list]) -> None:
    table.clear()
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        table.insertRow(r)
        for c, val in enumerate(row):
            item = QTableWidgetItem(str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


def _kpi_card(name: str) -> tuple[QFrame, QLabel]:
    frame = QFrame()
    set_class(frame, "card")
    lay = QVBoxLayout(frame)
    name_lbl = QLabel(name)
    set_class(name_lbl, "muted")
    value_lbl = QLabel("—")
    set_class(value_lbl, "kpi")
    lay.addWidget(name_lbl)
    lay.addWidget(value_lbl)
    return frame, value_lbl


class DayClosingScreen(BaseScreen):
    nav_title = "Day Closing"
    nav_permission = "shift_close"
    nav_order = 130

    def build_ui(self) -> None:
        self._shifts: list[dict] = []
        self._selected: dict | None = None

        root = QVBoxLayout(self)
        title = QLabel("Day Closing")
        set_class(title, "h1")
        root.addWidget(title)
        note = QLabel(
            "Day closing = close the day's open shift(s) and print the shift "
            "report. Select a shift below to review its sales before closing.")
        set_class(note, "muted")
        note.setWordWrap(True)
        root.addWidget(note)

        # -- date picker --
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Business day:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._load_day)
        ctrl_row.addWidget(self.date_edit)
        self.load_btn = QPushButton("Load")
        set_class(self.load_btn, "primary")
        self.load_btn.clicked.connect(self._load_day)
        ctrl_row.addWidget(self.load_btn)
        ctrl_row.addStretch(1)
        root.addLayout(ctrl_row)

        # -- shift list + summary side by side --
        main_row = QHBoxLayout()
        left = QVBoxLayout()
        left_lbl = QLabel("Shifts")
        set_class(left_lbl, "h2")
        left.addWidget(left_lbl)
        self.shift_list = QListWidget()
        self.shift_list.itemSelectionChanged.connect(self._on_shift_selected)
        left.addWidget(self.shift_list)
        main_row.addLayout(left, 1)

        right = QVBoxLayout()
        right_lbl = QLabel("Shift Summary")
        set_class(right_lbl, "h2")
        right.addWidget(right_lbl)
        self.summary_hint = QLabel("Select a shift to view its summary.")
        set_class(self.summary_hint, "muted")
        right.addWidget(self.summary_hint)

        kpi_row = QHBoxLayout()
        self._cards = {}
        for name in ("Transactions", "Gross", "Discount", "Tax", "Net"):
            frame, value_lbl = _kpi_card(name)
            self._cards[name] = value_lbl
            kpi_row.addWidget(frame)
        right.addLayout(kpi_row)

        self.cash_label = QLabel("")
        set_class(self.cash_label, "h2")
        right.addWidget(self.cash_label)

        type_lbl = QLabel("Sales by type")
        set_class(type_lbl, "h2")
        right.addWidget(type_lbl)
        self.type_table = QTableWidget()
        self.type_table.setAlternatingRowColors(True)
        right.addWidget(self.type_table)

        method_lbl = QLabel("Payments by method")
        set_class(method_lbl, "h2")
        right.addWidget(method_lbl)
        self.method_table = QTableWidget()
        self.method_table.setAlternatingRowColors(True)
        right.addWidget(self.method_table)

        btn_row = QHBoxLayout()
        self.print_btn = QPushButton("Print Report")
        set_class(self.print_btn, "primary")
        self.print_btn.clicked.connect(self._do_print_report)
        self.close_btn = QPushButton("Close Shift")
        set_class(self.close_btn, "danger")
        self.close_btn.clicked.connect(self._do_close_shift)
        btn_row.addWidget(self.print_btn)
        btn_row.addWidget(self.close_btn)
        btn_row.addStretch(1)
        right.addLayout(btn_row)
        self.gate(self.print_btn, "shift_close")
        self.gate(self.close_btn, "shift_close")
        main_row.addLayout(right, 2)
        root.addLayout(main_row)

    def on_show(self) -> None:
        self._load_day()

    # -- data ------------------------------------------------------------------
    def _day_str(self) -> str:
        return self.date_edit.date().toString("yyyy-MM-dd")

    def _load_day(self) -> None:
        self._selected = None
        shifts = self.safe(self._fetch_shifts)
        if shifts is None:
            return
        self._shifts = shifts
        self.shift_list.clear()
        for sh in shifts:
            item = QListWidgetItem(
                f"Shift #{sh['id']} — {sh['status'].upper()} — "
                f"opened {sh['opened_at']}")
            item.setData(Qt.ItemDataRole.UserRole, sh["id"])
            self.shift_list.addItem(item)
        if not shifts:
            self.shift_list.addItem(QListWidgetItem("No shifts for this day."))
        self._clear_summary()
        self._update_buttons()

    def _fetch_shifts(self) -> list[dict]:
        day = self._day_str()
        with self.db() as s:
            rows = (s.query(models.Shift)
                    .filter_by(business_day=day)
                    .order_by(models.Shift.id).all())
            return [{
                "id": sh.id,
                "status": sh.status,
                "business_day": sh.business_day,
                "opened_at": (sh.opened_at.strftime("%d-%m-%Y %H:%M")
                              if sh.opened_at else "—"),
                "opened_by_id": sh.opened_by,
                "opening_cash": q(sh.opening_cash or 0),
                "closed_at": (sh.closed_at.strftime("%d-%m-%Y %H:%M")
                              if sh.closed_at else "—"),
                "expected_cash": q(sh.expected_cash) if sh.expected_cash is not None else None,
                "counted": (q(sh.closing_cash_counted)
                            if sh.closing_cash_counted is not None else None),
                "variance": q(sh.variance) if sh.variance is not None else None,
            } for sh in rows]

    def _on_shift_selected(self) -> None:
        items = self.shift_list.selectedItems()
        if not items:
            self._selected = None
            self._clear_summary()
            self._update_buttons()
            return
        shift_id = items[0].data(Qt.ItemDataRole.UserRole)
        if shift_id is None:
            return
        self._selected = next((s for s in self._shifts if s["id"] == shift_id), None)
        data = self.safe(self._fetch_summary, shift_id)
        if data is None:
            return
        self._render_summary(data)
        self._update_buttons()

    def _fetch_summary(self, shift_id: int) -> dict:
        with self.db() as s:
            svc = self.svc(s)
            summary = svc.shifts.shift_summary(shift_id)
            sh = summary["shift"]
            opener = s.get(models.User, sh.opened_by)
            closer = s.get(models.User, sh.closed_by) if sh.closed_by else None
            type_rows = [[t, v["count"], self.money(v["total"])]
                         for t, v in sorted(summary["by_type"].items())]
            method_rows = [[m, self.money(total)]
                           for m, total in sorted(summary["by_method"].items())]
            return {
                "shift": {
                    "id": sh.id,
                    "business_day": sh.business_day,
                    "status": sh.status,
                    "opened_by": (opener.full_name or opener.username) if opener else "—",
                    "opened_at": (sh.opened_at.strftime("%d-%m-%Y %H:%M")
                                  if sh.opened_at else "—"),
                    "opening_cash": q(sh.opening_cash or 0),
                    "closed_by": ((closer.full_name or closer.username)
                                  if closer else "—"),
                    "closed_at": (sh.closed_at.strftime("%d-%m-%Y %H:%M")
                                  if sh.closed_at else "—"),
                },
                "sales_count": summary["sales_count"],
                "gross": summary["gross"],
                "discount": summary["discount"],
                "tax": summary["tax"],
                "net": summary["net"],
                "type_rows": type_rows,
                "method_rows": method_rows,
                "expected_cash": summary["expected_cash"],
            }

    def _render_summary(self, data: dict) -> None:
        sh = data["shift"]
        self.summary_hint.setText(
            f"Shift #{sh['id']} — {sh['business_day']} — {sh['status'].upper()} "
            f"(opened by {sh['opened_by']} at {sh['opened_at']})")
        self._cards["Transactions"].setText(str(data["sales_count"]))
        self._cards["Gross"].setText(self.money(data["gross"]))
        self._cards["Discount"].setText(self.money(data["discount"]))
        self._cards["Tax"].setText(self.money(data["tax"]))
        self._cards["Net"].setText(self.money(data["net"]))
        sel = self._selected or {}
        expected = data["expected_cash"]
        counted = sel.get("counted")
        variance = sel.get("variance")
        cash_line = f"Expected cash: {self.money(expected)}"
        if counted is not None:
            cash_line += f"  |  Counted: {self.money(counted)}"
        if variance is not None:
            cash_line += f"  |  Variance: {self.money(variance)}"
        self.cash_label.setText(cash_line)
        _fill_table(self.type_table, ["Sale type", "Count", "Total"], data["type_rows"])
        _fill_table(self.method_table, ["Method", "Total"], data["method_rows"])

    def _clear_summary(self) -> None:
        self.summary_hint.setText("Select a shift to view its summary.")
        for lbl in self._cards.values():
            lbl.setText("—")
        self.cash_label.setText("")
        _fill_table(self.type_table, ["Sale type", "Count", "Total"], [])
        _fill_table(self.method_table, ["Method", "Total"], [])

    def _update_buttons(self) -> None:
        has = self._selected is not None
        self.print_btn.setEnabled(has)
        self.close_btn.setEnabled(has and self._selected.get("status") == "open")

    # -- actions -----------------------------------------------------------------
    def _refresh_chrome(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "refresh_chrome"):
            w.refresh_chrome()

    def _do_print_report(self) -> None:
        if self._selected is None:
            return
        shift_id = self._selected["id"]

        def do() -> tuple | None:
            with self.db() as s:
                svc = self.svc(s)
                summary = svc.shifts.shift_summary(shift_id)
                text = svc.printing.shift_report(shift_id, summary)
                printer = get_setting(s, "receipt_printer", "")
                return shift_id, text, printer

        res = self.safe(do)
        if not res:
            return
        sid, text, printer = res
        TextPreviewDialog(self, f"Shift #{sid} Report", text, printer).exec()

    def _do_close_shift(self) -> None:
        if self._selected is None or self._selected.get("status") != "open":
            self.warn("Select an open shift first.")
            return
        shift_id = self._selected["id"]
        expected = self.safe(self._expected_cash, shift_id)
        if expected is None:
            return
        dlg = CloseShiftDialog(self, expected)
        if not dlg.exec() or dlg.counted is None:
            return

        def do() -> tuple | None:
            with self.db() as s:
                svc = self.svc(s)
                svc.shifts.close_shift(shift_id, dlg.counted, self.ctx.actor(s))
                summary = svc.shifts.shift_summary(shift_id)
                text = svc.printing.shift_report(shift_id, summary)
                printer = get_setting(s, "receipt_printer", "")
                return shift_id, text, printer

        res = self.safe(do)
        if not res:
            return
        sid, text, printer = res
        self.info(f"Shift #{sid} closed.")
        TextPreviewDialog(self, f"Shift #{sid} Report", text, printer).exec()
        self._load_day()
        self._refresh_chrome()

    def _expected_cash(self, shift_id: int):
        with self.db() as s:
            return self.svc(s).shifts.expected_cash(shift_id)
