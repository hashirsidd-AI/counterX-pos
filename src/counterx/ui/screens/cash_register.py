"""Cash Register screen: live drawer status, cash moves and expenses."""
from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from ... import models
from ...utils.money import d, q
from ..base import BaseScreen
from ..dialogs import CashMoveDialog, ExpenseDialog
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


class CashRegisterScreen(BaseScreen):
    nav_title = "Cash Register"
    nav_permission = "cash_moves"
    nav_order = 110

    def build_ui(self) -> None:
        self._shift_id: int | None = None

        root = QVBoxLayout(self)
        title = QLabel("Cash Register")
        set_class(title, "h1")
        root.addWidget(title)

        self.status_label = QLabel("No shift is open.")
        set_class(self.status_label, "muted")
        root.addWidget(self.status_label)

        # KPI cards
        cards_row = QHBoxLayout()
        self._cards = {}
        for name in ("Opening Cash", "Cash In", "Cash Out", "Expenses",
                     "Expected Cash"):
            frame, value_lbl = _kpi_card(name)
            self._cards[name] = value_lbl
            cards_row.addWidget(frame)
        root.addLayout(cards_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self.cash_in_btn = QPushButton("Cash In")
        set_class(self.cash_in_btn, "primary")
        self.cash_in_btn.clicked.connect(self._do_cash_in)
        self.cash_out_btn = QPushButton("Cash Out")
        self.cash_out_btn.clicked.connect(self._do_cash_out)
        self.expense_btn = QPushButton("Record Expense")
        self.expense_btn.clicked.connect(self._do_expense)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.on_show)
        btn_row.addWidget(self.cash_in_btn)
        btn_row.addWidget(self.cash_out_btn)
        btn_row.addWidget(self.expense_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(refresh_btn)
        root.addLayout(btn_row)
        self.gate(self.cash_in_btn, "cash_moves")
        self.gate(self.cash_out_btn, "cash_moves")
        self.gate(self.expense_btn, "expenses")

        # Tables
        moves_title = QLabel("Cash Moves")
        set_class(moves_title, "h2")
        root.addWidget(moves_title)
        self.moves_table = QTableWidget()
        self.moves_table.setAlternatingRowColors(True)
        root.addWidget(self.moves_table)

        expenses_title = QLabel("Expenses")
        set_class(expenses_title, "h2")
        root.addWidget(expenses_title)
        self.expenses_table = QTableWidget()
        self.expenses_table.setAlternatingRowColors(True)
        root.addWidget(self.expenses_table)

    def on_show(self) -> None:
        self._load()

    # -- data ------------------------------------------------------------------
    def _load(self) -> None:
        data = self.safe(self._fetch)
        if data is None:
            return
        if data["shift"] is None:
            self._shift_id = None
            self.status_label.setText("No shift is open.")
            for lbl in self._cards.values():
                lbl.setText("—")
            self.cash_in_btn.setEnabled(False)
            self.cash_out_btn.setEnabled(False)
            self.expense_btn.setEnabled(False)
            _fill_table(self.moves_table, ["Time", "Type", "Amount", "Reason", "By"], [])
            _fill_table(self.expenses_table,
                        ["Time", "Category", "Amount", "Note", "By"], [])
            return

        sh = data["shift"]
        self._shift_id = sh["id"]
        self.status_label.setText(
            f"Shift #{sh['id']} — {sh['business_day']} — opened by {sh['opened_by']} "
            f"at {sh['opened_at']}")
        self.cash_in_btn.setEnabled(True)
        self.cash_out_btn.setEnabled(True)
        self.expense_btn.setEnabled(True)
        self._cards["Opening Cash"].setText(self.money(sh["opening_cash"]))
        self._cards["Cash In"].setText(self.money(data["cash_in_total"]))
        self._cards["Cash Out"].setText(self.money(data["cash_out_total"]))
        self._cards["Expenses"].setText(self.money(data["expense_total"]))
        self._cards["Expected Cash"].setText(self.money(data["expected_cash"]))
        _fill_table(self.moves_table, ["Time", "Type", "Amount", "Reason", "By"],
                    data["moves"])
        _fill_table(self.expenses_table, ["Time", "Category", "Amount", "Note", "By"],
                    data["expenses"])

    def _fetch(self) -> dict:
        with self.db() as s:
            svc = self.svc(s)
            shift = svc.shifts.current_shift()
            if shift is None:
                return {"shift": None}
            sid = shift.id
            expected = svc.shifts.expected_cash(sid)
            moves = (s.query(models.CashMove)
                     .filter_by(shift_id=sid)
                     .order_by(models.CashMove.created_at.desc(),
                               models.CashMove.id.desc()).all())
            expenses = (s.query(models.Expense)
                        .filter_by(shift_id=sid)
                        .order_by(models.Expense.created_at.desc(),
                                  models.Expense.id.desc()).all())
            user_ids = {m.user_id for m in moves} | {e.user_id for e in expenses}
            users = (s.query(models.User).filter(models.User.id.in_(user_ids)).all()
                     if user_ids else [])
            names = {u.id: (u.full_name or u.username) for u in users}
            move_rows, exp_rows = [], []
            cash_in_total = cash_out_total = exp_total = Decimal("0")
            for m in moves:
                amt = q(m.amount)
                if m.move_type == "cash_in":
                    cash_in_total += amt
                else:
                    cash_out_total += amt
                move_rows.append([
                    m.created_at.strftime("%d-%m-%Y %H:%M") if m.created_at else "—",
                    "Cash In" if m.move_type == "cash_in" else "Cash Out",
                    self.money(amt), m.reason or "—",
                    names.get(m.user_id, "—")])
            for e in expenses:
                amt = q(e.amount)
                exp_total += amt
                exp_rows.append([
                    e.created_at.strftime("%d-%m-%Y %H:%M") if e.created_at else "—",
                    e.category or "General", self.money(amt),
                    e.note or "—", names.get(e.user_id, "—")])
            opener = names.get(shift.opened_by, "—")
            return {
                "shift": {
                    "id": sid,
                    "business_day": shift.business_day,
                    "opened_at": (shift.opened_at.strftime("%d-%m-%Y %H:%M")
                                  if shift.opened_at else "—"),
                    "opened_by": opener,
                    "opening_cash": q(shift.opening_cash),
                },
                "expected_cash": expected,
                "cash_in_total": q(cash_in_total),
                "cash_out_total": q(cash_out_total),
                "expense_total": q(exp_total),
                "moves": move_rows,
                "expenses": exp_rows,
            }

    # -- actions -----------------------------------------------------------------
    def _refresh_chrome(self) -> None:
        w = self.window()
        if w is not None and hasattr(w, "refresh_chrome"):
            w.refresh_chrome()

    def _do_cash_in(self) -> None:
        self._do_cash_move("cash_in")

    def _do_cash_out(self) -> None:
        self._do_cash_move("cash_out")

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
