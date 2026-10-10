"""Application stylesheet built from config.THEME.

Official palette: Midnight Navy + Teal + White.
Sidebar is dark navy, workspace is soft off-white, teal marks primary
actions and active selection. Widgets opt into variants with
``set_class(widget, "primary" | "danger" | "ghost" | "h1" | "h2" | "muted" | "card" | "kpi")``.
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ..config import THEME


def set_class(widget: QWidget, name: str) -> None:
    """Assign a style class via dynamic property and repolish the widget."""
    widget.setProperty("cssClass", name)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def get_stylesheet() -> str:
    t = THEME
    return f"""
/* ============ base ============ */
* {{
    font-family: "Segoe UI", "Noto Sans", "Jameel Noori Nastaleeq", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background: {t['workspace_bg']};
    color: {t['text_main']};
}}
QLabel[cssClass="h1"] {{
    font-size: 20px; font-weight: 700; color: {t['text_main']};
}}
QLabel[cssClass="h2"] {{
    font-size: 15px; font-weight: 700; color: {t['text_main']};
}}
QLabel[cssClass="muted"] {{
    color: {t['text_secondary']};
}}
QLabel[cssClass="kpi"] {{
    font-size: 24px; font-weight: 700; color: {t['navy_bg']};
}}
QFrame[cssClass="card"] {{
    background: {t['white']};
    border: 1px solid {t['border']};
    border-radius: 8px;
}}

/* ============ sidebar ============ */
QWidget#Sidebar {{
    background: {t['navy_bg']};
}}
QLabel#BrandLabel {{
    color: {t['white']};
    font-size: 20px; font-weight: 800;
}}
QLabel#BrandSub {{
    color: #9FB0C7;
    font-size: 11px;
}}
QPushButton#NavButton {{
    background: transparent;
    color: #C9D5E6;
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
}}
QPushButton#NavButton:hover {{
    background: #1E334E;
    color: {t['white']};
}}
QPushButton#NavButton:checked {{
    background: {t['teal']};
    color: {t['white']};
    font-weight: 600;
}}

/* ============ buttons ============ */
QPushButton {{
    background: {t['white']};
    color: {t['text_main']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton:hover {{
    border-color: {t['teal']};
}}
QPushButton:pressed {{
    background: #EDF1F6;
}}
QPushButton:disabled {{
    color: #A5B0C2;
    background: #F0F3F7;
}}
QPushButton[cssClass="primary"] {{
    background: {t['teal']};
    color: {t['white']};
    border: none;
    font-weight: 600;
}}
QPushButton[cssClass="primary"]:hover {{
    background: {t['teal_dark']};
}}
QPushButton[cssClass="danger"] {{
    background: {t['danger']};
    color: {t['white']};
    border: none;
    font-weight: 600;
}}
QPushButton[cssClass="ghost"] {{
    background: transparent;
    border: none;
    color: {t['teal']};
    font-weight: 600;
}}

/* ============ inputs ============ */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {{
    background: {t['white']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: {t['teal']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {t['teal']};
}}
QComboBox QAbstractItemView {{
    background: {t['white']};
    border: 1px solid {t['border']};
    selection-background-color: {t['teal']};
    selection-color: {t['white']};
}}

/* ============ tables ============ */
QTableWidget {{
    background: {t['white']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    gridline-color: {t['border']};
    alternate-background-color: #F8FAFC;
    selection-background-color: #D9EFEC;
}}
QTableWidget::item:selected {{
    background: #D7EFEA;
    color: {t['text_main']};
}}
QHeaderView::section {{
    background: {t['navy_bg']};
    color: {t['white']};
    border: none;
    padding: 8px 10px;
    font-weight: 600;
}}

/* ============ tabs / misc ============ */
QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    background: {t['white']};
}}
QTabBar::tab {{
    background: transparent;
    color: {t['text_secondary']};
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background: {t['white']};
    color: {t['teal']};
    border-bottom: 2px solid {t['teal']};
}}
QDialog {{
    background: {t['workspace_bg']};
}}
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 12px;
    background: {t['white']};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {t['text_secondary']};
}}
QStatusBar {{
    background: {t['navy_dark']};
    color: #C9D5E6;
}}
QStatusBar QLabel {{
    color: #C9D5E6;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #C3CEDD;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QToolTip {{
    background: {t['navy_bg']};
    color: {t['white']};
    border: none;
    padding: 6px;
}}
"""
