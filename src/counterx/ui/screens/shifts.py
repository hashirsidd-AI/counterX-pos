"""Shift Management screen: open/close shift and shift history."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ... import models  # noqa: F401  (model fields accessed via services)
from ...utils.money import d, q
from ..base import BaseScreen, get_setting
from ..dialogs import (
    CashMoveDialog, CloseShiftDialog, ExpenseDialog, TextPreviewDialog,
)
from ..theme import set_class


def _fill_table(table: QTableWidget, headers: list[str],
                rows: list[list],
                variance_col: int | None = None) -> None:
    table.clear()
    table.setRowCount(0)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    for r, row in enumerate(rows):
        table.insertRow(r)
        for c, val in enumerate(row):
            item = QTableWidgetItem(str(val))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if variance_col is not None and c == variance_col:
                try:
                    v = d(val)
                    if v < 0:
                        item.setForeground(QColor("#D64545"))
                    elif v > 0:
                        item.setForeground(QColor("#1E9E6A"))
                except Exception:  # noqa: BLE001
                    pass
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


class ShiftsScreen(BaseScreen):
    nav_title = "Shift Management"
    nav_permission = "sell"
    nav_order = 120

    def build_ui(self) -> None:
        self._shift_id: int | None = None

        root = QVBoxLayout(self)
        title = QLabel("Shift Management")
        set_class(title, "h1")
        root.addWidget(title)

        # -- current shift card --
        card = QFrame()
        set_class(card, "card")
        card_lay = QVBoxLayout(card)
        card_head = QLabel("Current Shift")
        set_class(card_head, "h2")
        card_lay.addWidget(card_head)

        self.shift_info = QLabel("")
        self.shift_info.setWordWrap(True)
        card_lay.addWidget(self.shift_info)

        self.shift_kpis = QLabel("")
        set_class(self.shift_kpis, "h2")
        card_lay.addWidget(self.shift_kpis)

        btn_row = QHBoxLayout()
        self.open_shift_btn = QPushButton("Open Shift")
        set_class(self.open_shift_btn, "primary")
        self.open_shift_btn.clicked.connect(self._do_open_shift)
        self.cash_in_btn = QPushButton("Cash In")
        self.cash_in_btn.clicked.connect(lambda: self._do_cash_move("cash_in"))
        self.cash_out_btn = QPushButton("Cash Out")
        self.cash_out_btn.clicked.connect(lambda: self._do_cash_move("cash_out"))
        self.expense_btn = QPushButton("Record Expense")
        self.expense_btn.clicked.connect(self._do_expense)
        self.close_shift_btn = QPushButton("Close Shift")
        set_class(self.close_shift_btn, "danger")
        self.close_shift_btn.clicked.connect(self._do_close_shift)
        btn_row.addWidget(self.open_shift_btn)
        btn_row.addWidget(self.cash_in_btn)
        btn_row.addWidget(self.cash_out_btn)
        btn_row.addWidget(self.expense_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_shift_btn)
        card_lay.addLayout(btn_row)
        root.addWidget(card)

        self.gate(self.open_shift_btn, "sell")
        self.gate(self.cash_in_btn, "cash_moves")
        self.gate(self.cash_out_btn, "cash_moves")
        self.gate(self.expense_btn, "expenses")
        self.gate(self.close_shift_btn, "shift_close")

        # -- history --
        hist_title = QLabel("Shift History")
        set_class(hist_title, "h2")
        root.addWidget(hist_title)
        self.history_table = QTableWidget()
        self.history_table.setAlternatingRowColors(True)
        root.addWidget(self.history_table)

    def on_show(self) -> None:
        self._load()

    # -- data ------------------------------------------------------------------
    def _load(self) -> None:
        data = self.safe(self._fetch)
        if data is None:
            return
        sh = data["current"]
        if sh is None:
            self._shift_id = None
            self.shift_info.setText("No shift is currently open.")
            self.shift_kpis.setText("")
            self.open_shift_btn.setEnabled(True)
            self.cash_in_btn.setEnabled(False)
            self.cash_out_btn.setEnabled(False)
            self.expense_btn.setEnabled(False)
            self.close_shift_btn.setEnabled(False)
        else:
            self._shift_id = sh["id"]
            self.shift_info.setText(
                f"Shift #{sh['id']}  |  Day: {sh['business_day']}  |  "
                f"Opened: {sh['opened_at']} by {sh['opened_by']}  |  "
                f"Opening cash: {self.money(sh['opening_cash'])}")
            self.shift_kpis.setText(
                f"Expected cash in drawer: {self.money(sh['expected_cash'])}")
            self.open_shift_btn.setEnabled(False)
            self.cash_in_btn.setEnabled(True)
            self.cash_out_btn.setEnabled(True)
            self.expense_btn.setEnabled(True)
            self.close_shift_btn.setEnabled(True)
        _fill_table(
            self.history_table,
            ["ID", "Day", "Opened", "Closed", "Opening", "Expected", "Counted",
             "Variance", "Status"],
            data["history"], variance_col=7)

    def _fetch(self) -> dict:
        with self.db() as s:
            svc = self.svc(s)
            shift = svc.shifts.current_shift()
            current = None
            if shift is not None:
                opener = s.get(models.User, shift.opened_by)
                current = {
                    "id": shift.id,
                    "business_day": shift.business_day,
                    "opened_at": (shift.opened_at.strftime("%d-%m-%Y %H:%M")
                                  if shift.opened_at else "—"),
                    "opened_by": ((opener.full_name or opener.username)
                                  if opener else "—"),
                    "opening_cash": q(shift.opening_cash),
                    "expected_cash": svc.shifts.expected_cash(shift.id),
                }
            history = svc.shifts.shift_history(50)
            rows = []
            for sh in history:
                rows.append([
                    sh.id,
                    sh.business_day,
                    sh.opened_at.strftime("%d-%m-%Y %H:%M") if sh.opened_at else "—",
                    sh.closed_at.strftime("%d-%m-%Y %H:%M") if sh.closed_at else "—",
                    self.money(q(sh.opening_cash or 0)),
                    self.money(q(sh.expected_cash)) if sh.expected_cash is not None else "—",
                    self.money(q(sh.closing_cash_counted))
                    if sh.closing_cash_counted is not None else "—",
                    str(q(sh.variance)) if sh.variance is not None else "—",
                    sh.status,
                ])
            return {"current": current, "history": rows}

    # -- actions -----------------------------------------------------------------
    def _refresh_chrome(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "refresh_chrome"):
            w.refresh_chrome()

    def _do_open_shift(self) -> None:
        value, ok = QInputDialog.getDouble(
            self, "Open Shift", "Opening cash in drawer:", 0, 0, 100_000_000, 2)
        if not ok:
            return
        amount = q(value)

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                svc.shifts.open_shift(self.ctx.actor(s), amount)
            return True

        if not self.safe(do):
            return
        self.info(f"Shift opened with {self.money(amount)} in the drawer.")
        self._load()
        self._refresh_chrome()

    def _do_cash_move(self, mode: str) -> None:
        if self._shift_id is None:
            self.warn("No shift is open.")
            return
        dlg = CashMoveDialog(self, mode)
        if not dlg.exec() or dlg.result is None:
            return
        amount, reason = dlg.result

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                actor = self.ctx.actor(s)
                if mode == "cash_in":
                    svc.shifts.cash_in(self._shift_id, amount, actor, reason)
                else:
                    svc.shifts.cash_out(self._shift_id, amount, actor, reason)
            return True

        if not self.safe(do):
            return
        self._load()
        self._refresh_chrome()

    def _do_expense(self) -> None:
        if self._shift_id is None:
            self.warn("No shift is open.")
            return
        dlg = ExpenseDialog(self)
        if not dlg.exec() or dlg.result is None:
            return
        category, amount, note = dlg.result

        def do() -> bool:
            with self.db() as s:
                svc = self.svc(s)
                svc.shifts.add_expense(self._shift_id, category, amount,
                                       self.ctx.actor(s), note)
            return True

        if not self.safe(do):
            return
        self._load()
        self._refresh_chrome()

    def _do_close_shift(self) -> None:
        if self._shift_id is None:
            self.warn("No shift is open.")
            return
        shift_id = self._shift_id
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
        self._load()
        self._refresh_chrome()

    def _expected_cash(self, shift_id: int) -> Decimal:
        with self.db() as s:
            return self.svc(s).shifts.expected_cash(shift_id)
