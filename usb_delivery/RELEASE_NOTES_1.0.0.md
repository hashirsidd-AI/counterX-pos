# counterX POS — Release Notes v1.0.0

**Release date:** October 2026
**Company:** counterX — +92 315 7988387 | +44 7878 921068

## What's included

**Complete offline desktop POS** (native Windows application — not a website, no browser needed):

- **19 screens:** Dashboard, New Sale, Products & Menu, Categories & Modifiers, Inventory & Stock, Orders & History, Customers, Suppliers, Purchases, Expenses, Cash Register, Shift Management, Day Closing, Reports & Analytics, Employees & Permissions, Printer Settings, Business Settings, Database & Backup, License & About.
- **Billing:** fast product search (name/SKU/barcode), cart with quantities, item and order discounts, configurable tax, cash/card/bank-transfer/split payments, cash tendered and change, hold & resume, unique invoice numbers, receipt and kitchen-ticket (KOT) printing, reprints.
- **Shifts & cash control:** shift open/close with opening cash, expected-vs-counted cash with shortage/overage, cash in/out, expenses, locked shift history, day closing.
- **Inventory:** products with cost/selling price, stock tracking, purchases from suppliers, adjustments, movement ledger, low-stock alerts.
- **Users & permissions:** Owner / Manager / Cashier roles, enforced in the business logic — not just hidden buttons. Full audit trail.
- **Reports:** daily and date-range sales, cashier performance, product/category sales, payment breakdown, discounts, returns, tax summaries, estimated profit.
- **Backup & restore:** one-click backup with integrity validation, automatic backups, USB copy, safe restore (automatic safety backup first).
- **Pakistan defaults:** Rupee (Rs / PKR) formatting, cash-first workflows, configurable tax rates, English + Urdu product names and receipts.
- **Offline licensing:** per-computer license keys verified locally; no internet required.
- **Data safety:** local SQLite database with migrations — uninstalls and upgrades preserve business data.

**Quality checks done:** 49/49 automated engine tests passing; UI screens smoke-tested offscreen (see `documentation/UI_TEST_NOTES.md` in the project).

## Known limitations (please read)

1. **The Windows installer is not included as a finished file.** The `.exe` and `counterX-POS-Setup-1.0.0.exe` must be built on a real Windows 10/11 PC by running `installer\build_windows.bat` from the project source. This package contains the complete source and build scripts — not the binary.
2. **Physical receipt-printer testing was not done.** Printing code is written for standard Windows printers, but no physical printer was available during development. Test with the client's actual printer model before promising anything.
3. **Barcode-scanner hardware was not tested.** The scan-to-search path is implemented (scanner acts as keyboard + Enter), but no physical scanner was used in testing.
4. **Single computer only in v1.0.0.** The database is SQLite on one PC. There is no live sync between multiple computers in this version.
5. **Profit figures are estimates.** Reports label estimated gross profit as an estimate, because not every cost may be recorded.
6. **Urdu display depends on the PC's fonts.** Urdu text flows through the app correctly, but the client PC needs an Urdu-capable font installed — verify visually on each client machine.
7. **No tax/regulatory compliance is claimed.** Tax rates and invoice fields are fully configurable, but FBR/SRB/PRA compliance must be verified by the client or their accountant against their actual legal requirements.
8. **Offline licensing** stops casual copying but is not uncrackable DRM (see LICENSE_INFO.md).

## Upgrading from this version

Future versions will migrate your database automatically — your sales, products, and settings are preserved. Always take a backup before upgrading.

## New in this build: optional Supabase cloud sync (offline-first)
- Local SQLite stays the system of record; billing works fully offline.
- Background worker uploads sales, products, stock moves, shifts, expenses
  and more when internet is available. Idempotent, retrying, never blocks billing.
- Cloud Sync screen: status, pending/failed counts, manual Sync Now.
- Setup: see documentation/SUPABASE_SETUP.md (run the SQL once, enter URL +
  anon key in the app). No service-role key in the app; businesses isolated
  by installation ID. v1 is one-way backup (local → cloud); multi-terminal
  live sync is not included.
