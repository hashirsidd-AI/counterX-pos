"""Application-wide configuration: paths, branding, theme, business defaults."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "counterX POS"
APP_SLUG = "counterx"
COMPANY_NAME = "counterX"
COMPANY_PHONES = ["+92 315 7988387", "+44 7878 921068"]
APP_VERSION = "1.1.0"
BUILD_NUMBER = "110"

# --- Official colour theme: Midnight Navy + Teal + White ---------------------
THEME = {
    "navy_bg": "#14243A",      # primary background / sidebar
    "navy_dark": "#0E1A2B",    # darker navy for headers
    "workspace_bg": "#F5F7FA",  # main workspace background
    "teal": "#0F9D8A",         # primary action / active selection
    "teal_dark": "#0B7A6C",    # teal hover/pressed
    "text_main": "#253247",    # main text
    "text_secondary": "#697586",  # secondary text
    "border": "#E1E7EF",       # borders and separators
    "white": "#FFFFFF",
    "success": "#1E9E6A",
    "warning": "#D99413",
    "danger": "#D64545",
}

# --- Filesystem locations ----------------------------------------------------
def _data_root() -> Path:
    """Per-user writable data directory (database, backups, logs live here)."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "counterX"
    # Linux/macOS (dev only)
    return Path.home() / ".local" / "share" / "counterx"


DATA_ROOT = _data_root()
DB_PATH = DATA_ROOT / "data" / "counterx.db"
BACKUP_DIR = DATA_ROOT / "backups"
LOG_DIR = DATA_ROOT / "logs"
RECEIPT_DIR = DATA_ROOT / "receipts"

for _p in (DB_PATH.parent, BACKUP_DIR, LOG_DIR, RECEIPT_DIR):
    _p.mkdir(parents=True, exist_ok=True)

# --- Business defaults (Pakistan) --------------------------------------------
DEFAULT_CURRENCY_SYMBOL = "Rs"
DEFAULT_CURRENCY_CODE = "PKR"
DEFAULT_TAX_RATE = 0  # no tax assumed until the business configures it
SALE_TYPES = ("dine_in", "takeaway", "delivery", "online")
PAYMENT_METHODS = ("cash", "card", "bank_transfer")
ROLES = ("owner", "manager", "cashier")

# Permission catalogue. Enforced in the service layer, not just the UI.
PERMISSIONS = (
    "sell",            # run the POS and complete cash sales
    "discount",        # apply item/order discounts
    "refund",          # process refunds
    "void",            # void a completed sale
    "price_change",    # edit selling price at the till
    "stock_adjust",    # manual stock adjustments / counts
    "expenses",        # record expenses and cash in/out
    "cash_moves",      # cash-in / cash-out
    "shift_close",     # close shifts and day
    "reports",         # view reports
    "products",        # manage products, categories, prices
    "purchases",       # suppliers and purchase receiving
    "users",           # manage users and permissions
    "settings",        # business settings and tax configuration
    "backup",          # backup and restore
    "license",         # license screen
)

ROLE_PERMISSIONS: dict[str, frozenset] = {
    "owner": frozenset(PERMISSIONS),
    "manager": frozenset(p for p in PERMISSIONS if p not in ("users", "license", "settings")),
    "cashier": frozenset(("sell",)),
}
