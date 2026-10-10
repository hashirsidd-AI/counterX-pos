# counterX POS v1.0.0 — Release Report

**Date:** 2026-10-10
**Company:** counterX — +92 315 7988387, +44 7878 921068
**Status:** Source-complete. Windows `.exe` / installer must be built on a
Windows PC (see §5 — honest limitation, not a missing file by accident).

## 1. What was delivered

Complete offline-first Windows desktop POS for the Pakistani market
(Python 3.10+, PySide6, SQLite, SQLAlchemy). 60+ source files in
`~/workspace/counterX-POS/`.

**Application (20 screens):** Login, Dashboard, New Sale/POS (categories,
barcode/Enter search, item cards, cart steppers, permission-gated discounts,
order types, table+waiter, Hold/Resume, checkout with Cash/Card/Bank/Split,
receipt preview, KOT print), Products & Menu, Categories & Modifiers,
Inventory & Stock, Orders & History (reprint/refund/void), Customers,
Suppliers, Purchases, Expenses, Cash Register, Shift Management, Day Closing,
Reports & Analytics (9 report types, CSV export), Employees & Permissions,
Printer Settings, Business Settings (configurable tax rates — nothing
hardcoded), Database & Backup, Cloud Sync, License & About.

**First-run wizard:** business name/type (Restaurant/Cafe/Bakery/Retail),
logo picker, address/phones, configurable tax rate, receipt footer,
auto-backup preference, owner account creation (no default password —
owner chooses their own), one-time owner recovery code shown once.

**Security:** PBKDF2 password hashing (no plaintext), role-based permissions
(owner/manager/cashier) enforced in the service layer, per-user
grant/revoke overrides, owner recovery via hashed recovery code, audit log
on all sensitive actions.

**Offline-first Supabase sync (optional):** local SQLite is the system of
record; mutations write to a `sync_queue` outbox in the same transaction;
a background worker uploads oldest-first when online. Billing never waits
for the cloud. Idempotent uploads (`sync_uuid` + `on_conflict`), immutable
financial records (first-write-wins), mutable master data (last-write-wins),
exponential-backoff retries, per-row error visibility, manual Sync Now,
Cloud Sync status screen. Anon-key only in the app — **no service-role key
ever embedded**; per-installation Supabase Auth user; RLS isolates
businesses by `installation_id`; passwords/hashes never uploaded.
See `documentation/SUPABASE_SETUP.md` (full SQL + RLS script).

**Packaging:** `installer/counterx.spec` (PyInstaller), `installer/counterx.iss`
(Inno Setup: Start Menu, optional desktop shortcut, uninstaller that never
deletes the database), `installer/build_windows.bat` (one-click build),
app icon (`assets/counterx.ico/.png`), USB docs (7 guides in `usb_delivery/`).

## 2. Actual test results (all executed, none invented)

| Suite | Result |
|---|---|
| `pytest tests/` — engine: auth, sales, shifts, inventory, reports, backup, licensing | 50/50 pass |
| `pytest tests/test_sync.py` — migration v1→v2, outbox, upload, retry/backoff, idempotency, immutable-vs-mutable conflicts, credential redaction, recovery codes | 13/13 pass |
| **Total pytest** | **63/63 pass** |
| Offscreen GUI smoke (19 screens + 7 dialogs instantiate; dashboard renders true figures incl. Urdu names) | 27/27 + 20/20 pass |
| Offscreen smoke, sync UI additions (SyncScreen registered, wizard/login/recovery dialogs, service status) | 4/4 pass |
| `py_compile` on all 60+ source files | pass |

Two real defects were found by verification and fixed: (1) held-sale
double-resume hole → `release_hold()` + test; (2) sync worker touching
detached ORM objects + non-idempotent migration → fixed + tests.

## 3. Honest limitations — what was NOT tested / does not exist here

1. **No Windows `.exe` or installer was produced in this Linux environment.**
   PyInstaller/Inno Setup require Windows. Everything needed is ready
   (`installer/build_windows.bat`); run it on Windows 10/11 64-bit.
2. **No live Supabase test.** Sync was tested against an in-memory
   `FakeTransport` implementing the same contract. The real Supabase
   project setup, RLS policies and network behavior still need a live test
   with actual credentials (which were never invented or stored here).
3. **No physical printer / barcode-scanner testing.** Code paths exist
   (win32print with file fallback; Enter-key scanner input); hardware
   untested.
4. **No multi-terminal live sync** — by design (documented). Cloud sync v1
   is one-way backup (local → cloud); download/restore from cloud is not
   implemented.
5. **No human click-through** of the GUI; dialogs were instantiated
   offscreen, not clicked.
6. Profit figures are labelled estimates; tax/regulatory compliance is not
   claimed — the client checklist requires the customer's accountant to
   verify tax configuration.

## 4. How to build the installer (on Windows)

```bat
installer\build_windows.bat
```
Produces `dist\counterX-POS-Setup-1.0.0.exe`. Database upgrades run the v2
migration automatically; customer data is preserved; uninstall never
deletes `%APPDATA%\counterX`.
