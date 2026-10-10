"""Module screens. Each file exposes one ``*Screen(BaseScreen)`` class.

Contract for every screen module:
- ``class XxxScreen(BaseScreen)`` with class attributes:
    nav_title      e.g. "Dashboard"
    nav_permission e.g. "reports" (None = visible to every logged-in user)
    nav_order      int used to sort the sidebar
- ``build_ui(self)`` creates widgets once; ``on_show(self)`` refreshes data.
- All DB work: ``with self.db() as s:`` then ``svc = self.svc(s)`` and call
  service methods (they enforce permissions; catch via ``self.safe(...)``).
- Never fabricate figures: every number comes from a service call.
"""
from .dashboard import DashboardScreen
from .pos import POSScreen
from .products import ProductsScreen
from .categories import CategoriesScreen
from .inventory import InventoryScreen
from .orders import OrdersScreen
from .customers import CustomersScreen
from .suppliers import SuppliersScreen
from .purchases import PurchasesScreen
from .expenses import ExpensesScreen
from .cash_register import CashRegisterScreen
from .shifts import ShiftsScreen
from .day_closing import DayClosingScreen
from .reports import ReportsScreen
from .employees import EmployeesScreen
from .printer_settings import PrinterSettingsScreen
from .business_settings import BusinessSettingsScreen
from .backup import BackupScreen
from .sync import SyncScreen
from .license import LicenseScreen

SCREENS = [
    DashboardScreen,
    POSScreen,
    ProductsScreen,
    CategoriesScreen,
    InventoryScreen,
    OrdersScreen,
    CustomersScreen,
    SuppliersScreen,
    PurchasesScreen,
    ExpensesScreen,
    CashRegisterScreen,
    ShiftsScreen,
    DayClosingScreen,
    ReportsScreen,
    EmployeesScreen,
    PrinterSettingsScreen,
    BusinessSettingsScreen,
    BackupScreen,
    SyncScreen,
    LicenseScreen,
]

__all__ = ["SCREENS"] + [c.__name__ for c in SCREENS]
