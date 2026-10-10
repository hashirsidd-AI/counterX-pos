"""Business-logic services. All permission checks live here, not in the UI."""
from .auth import AuthService, PermissionDenied, AuthenticationError
from .catalog import CatalogService
from .directory import DirectoryService
from .sales import SaleService, CartLine, Cart
from .inventory import InventoryService
from .shifts import ShiftService
from .reports import ReportService
from .backup import BackupService
from .licensing import LicenseService
from .printing import PrintService

__all__ = [
    "AuthService", "PermissionDenied", "AuthenticationError",
    "CatalogService", "DirectoryService", "SaleService", "CartLine", "Cart",
    "InventoryService", "ShiftService", "ReportService",
    "BackupService", "LicenseService", "PrintService",
]
