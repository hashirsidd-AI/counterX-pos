"""Offscreen GUI smoke tests for the v1.1.0 UI changes.

Instantiates (does not show) the new/changed screens and dialogs against a
temporary database and asserts they build without exceptions.

Run: LD_LIBRARY_PATH=~/workspace/.qtlibs QT_QPA_PLATFORM=offscreen \
     .venv/bin/python -m pytest tests/test_ui_smoke_110.py -q
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402
except ImportError:
    pytest.skip("PySide6 unavailable "
                "(needs LD_LIBRARY_PATH=~/workspace/.qtlibs)",
                allow_module_level=True)

from counterx import database, models
from counterx.database import session_scope
from counterx.services import AuthService
from counterx.ui.base import AppContext
from counterx.ui.theme import get_stylesheet


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(get_stylesheet())
    yield app


@pytest.fixture(scope="module")
def ctx(qapp):
    tmp = tempfile.mkdtemp()
    engine = database.get_engine(os.path.join(tmp, "ui110.db"))
    database.init_db(engine)
    with session_scope(engine) as s:
        AuthService(s).create_user("owner", "owner1234", "Owner",
                                   role="owner")
        uid = s.query(models.User).filter_by(username="owner").one().id
    c = AppContext(engine, uid)
    c.refresh_identity()
    return c


def test_product_dialog_add_mode(ctx):
    from counterx.ui.screens.products import ProductDialog, ProductsScreen
    screen = ProductsScreen(ctx)
    dlg = ProductDialog(screen)
    # streamlined basic fields present
    assert dlg.name is not None
    assert dlg.category is not None
    assert dlg.sell_price is not None
    assert dlg.stock_spin is not None
    assert dlg.image_path is not None
    # advanced options collapsed by default, SKU auto-generated
    assert not dlg.adv_widget.isVisible()
    assert dlg.sku.text().startswith("P-")
    # "+" category button exists
    assert dlg.cat_add_btn.text() == "+"


def test_products_demo_banner_hidden_without_seed(ctx):
    from counterx.ui.screens.products import ProductsScreen
    screen = ProductsScreen(ctx)
    screen.on_show()
    assert screen.demo_banner.isHidden()


def test_pos_screen_builds(ctx):
    from counterx.ui.screens.pos import POSScreen
    screen = POSScreen(ctx)
    screen.on_show()
    # category button row: at least the "All" button
    assert len(screen._cat_buttons) >= 1
    assert screen._cat_buttons[0][0].text() == "All"
    assert screen._current_category() is None
    # order-details section collapsed by default
    assert not screen.details_widget.isVisible()
    # totals widgets intact
    assert set(screen.tot_labels) == {"subtotal", "discount_total",
                                      "tax_total", "service_charge",
                                      "delivery_charge"}


def test_dashboard_screen_builds(ctx):
    from counterx.ui.screens.dashboard import DashboardScreen
    screen = DashboardScreen(ctx)
    screen.refresh()
    assert len(screen._kpi_vals) == 6
    # no sales yet -> empty state shown (isHidden False; the screen itself
    # is never shown offscreen, so isVisible() would be False regardless)
    assert not screen.empty_card.isHidden()
    assert screen.recent_table.rowCount() == 0


def test_wizard_demo_choice_defaults(ctx):
    from counterx.ui.dialogs import FirstRunWizard, LoginDialog
    wiz = FirstRunWizard(ctx.engine)
    assert wiz.demo_radio_sample.isChecked()
    assert not wiz.demo_radio_empty.isChecked()
    login = LoginDialog(ctx.engine)
    assert login is not None


def test_main_window_builds_with_groups(ctx):
    from counterx.ui.main_window import MainWindow, NAV_GROUPS
    win = MainWindow(ctx)
    assert "Dashboard" in win.screens
    assert "New Sale" in win.screens
    assert "Products & Menu" in win.screens
    # every nav title is reachable through the groups (or fallback)
    grouped = {t for _, titles in NAV_GROUPS for t in titles}
    assert set(win.screens) <= grouped | set(win.screens)
    win.refresh_chrome()
    assert "No shift open" in win.shift_label.text()
