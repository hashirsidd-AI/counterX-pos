"""Expenses screen: record and list business expenses."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from ... import models
from ...utils.money import d, fmt
from ..base import BaseScreen
from ..dialogs import ExpenseDialog
from ..theme import set_class


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class ExpensesScreen(BaseScreen):
    nav_title = "Expenses"
    nav_permission = "expenses"
    nav_order = 100

    def build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Expenses")
        set_class(title, "h1")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.record_btn = QPushButton("Record Expense")
        set_class(self.record_btn, "primary")
        self.record_btn.clicked.connect(self._record_expense)
        self.gate(self.record_btn, "expenses")
        toolbar.addWidget(self.record_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Category", "Amount", "Note", "Shift", "By"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

    def on_show(self) -> None:
        self.refresh()

    # -- data ------------------------------------------------------------------
    def refresh(self) -> None:
        def load():
            with self.db() as s:
                expenses = (s.query(models.Expense)
                            .order_by(models.Expense.created_at.desc(),
                                      models.Expense.id.desc())
                            .limit(500).all())
                return [{
                    "date": e.created_at.strftime("%Y-%m-%d %H:%M")
                            if e.created_at else "",
                    "category": e.category or "General",
                    "amount": d(e.amount or 0),
                    "note": e.note or "",
                    "shift": str(e.shift_id) if e.shift_id else "-",
                    "by": (u.username if (u := s.get(models.User, e.user_id)) else ""),
                } for e in expenses]

        rows = self.safe(load)
        if rows is None:
            return
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self.table.setItem(r, 0, _cell(row["date"]))
            self.table.setItem(r, 1, _cell(row["category"]))
            self.table.setItem(r, 2, _cell(fmt(row["amount"])))
            self.table.setItem(r, 3, _cell(row["note"]))
            self.table.setItem(r, 4, _cell(row["shift"]))
            self.table.setItem(r, 5, _cell(row["by"]))
        self.table.resizeColumnsToContents()

    # -- action ------------------------------------------------------------------
    def _record_expense(self) -> None:
        dlg = ExpenseDialog(self)
        if not (dlg.exec() and dlg.result):
            return
        category, amount, note = dlg.result

        def do():
            with self.db() as s:
                svc = self.svc(s)
                shift = svc.shifts.current_shift()
                if shift is None:
                    raise ValueError("Open a shift first — expenses must belong "
                                     "to an open shift.")
                return svc.shifts.add_expense(shift.id, category, amount,
                                              self.ctx.actor(s), note=note)

        expense = self.safe(do)
        if expense is not None:
            self.info(f"Expense recorded: {category} — {fmt(amount)}.")
            self.refresh()
