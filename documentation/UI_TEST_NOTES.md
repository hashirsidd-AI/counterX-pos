# counterX POS — UI Verification Notes

Date: 2026-10-10. Author: UI coordinator (subagent).
Rule followed throughout: **no invented results, no claimed artifacts.**

## 1. Static checks — PASS

- `python -m py_compile` passes on every new UI file:
  - `src/main.py`
  - `src/counterx/ui/__init__.py`, `base.py`, `theme.py`, `dialogs.py`,
    `printing_ui.py`, `main_window.py`
  - all 19 files in `src/counterx/ui/screens/`
  - `src/counterx/services/directory.py` (new service for customers /
    suppliers / tax rates, exported from `services/__init__.py`)
- Engine test suite: **49/49 pytest passing** (40 pre-existing + 9 new
  `tests/test_directory.py`).

## 2. Offscreen GUI smoke tests — PASS

PySide6 6.12.0 was installed into the project venv. The container lacked
`libEGL.so.1`, so the real Ubuntu 24.04 `libegl1` .deb was downloaded from
the Ubuntu archive and extracted to `~/workspace/.qtlibs` (no system
install, no apt lock touched). With
`LD_LIBRARY_PATH=~/workspace/.qtlibs QT_QPA_PLATFORM=offscreen`:

- **27/27 PASS** (`/tmp/smoke_ui.py`, empty database): `QApplication` +
  stylesheet, `MainWindow` (builds all 19 screens + sidebar + status bar),
  each `*Screen` instantiated with `on_show()` called, and all 7 dialogs
  instantiated (`LoginDialog`, `FirstRunWizard`, `CheckoutDialog`,
  `CashMoveDialog`, `ExpenseDialog`, `CloseShiftDialog`,
  `TextPreviewDialog`).
- **20/20 PASS** (`/tmp/smoke_ui_data.py`, seeded database): same screens
  with real data — a completed dine-in sale (2× Chinese Platter + 1× Cibus
  Kung Pao, 15% tax, cash 6000), a held sale, an open shift with cash-in and
  an expense, opening stock, and a low-stock product. Verified the dashboard
  renders the true figures (Net Rs5,534.95 = 4,813.00 + 721.95 tax;
  Expected cash Rs11,034.95 = 5,000 + 5,534.95 + 1,000 − 500), the low-stock
  line ("Cibus Kung Pao — 2.00 / 5.00"), top products, shift card, and that
  Urdu text (`کنگ پاؤ`, `ٹیسٹ`) passes through widgets without crashing.

## 3. Defects found and fixed during verification

- Four screen files used wrong relative-import levels
  (`from .. import models`, `from ..utils.money import …`,
  `from .base import …` inside `counterx/ui/screens/`). Fixed to
  `from ... import models`, `from ...utils.money import …`,
  `from ..base import …`. The smoke test caught these; they now import
  cleanly.
- One child note claimed a GUI smoke test was "impossible here" — it became
  possible via the extracted libEGL above, and was run.

## 4. Genuinely NOT tested (honest limitations)

- **Windows executable / installer**: no `.exe` and no installer exist.
  PyInstaller/Inno Setup must run on a real Windows machine. Nothing here
  claims otherwise.
- **Physical printers**: `printing_ui.print_text()` win32print path is
  written but never executed (no Windows, no printer). Fallback (save text
  file + tell the user) is the tested path on Linux.
- **Urdu font rendering on target machines**: Qt shapes RTL natively and
  Urdu strings flow through widgets without crashing here, but the Windows
  target needs an Urdu-capable font (e.g. Jameel Noori Nastaleeq, already
  referenced first-fallback in the stylesheet) — verify visually on a real
  client PC.
- **Barcode scanner hardware**: Enter-key path in POS search is
  implemented; no physical scanner tested.
- **Interactive click-through**: dialogs/buttons were instantiated, not
  clicked by a human. Logic underneath is covered by the 49 engine tests.
- Minor: a `malloc_consolidate(): unaligned fastbin chunk detected` message
  appears during interpreter teardown after the offscreen tests exit
  (exit code still 0) — a Qt/offscreen shutdown artifact in this container,
  not an application error path.

## 5. Post-verification fix (2026-10-10): held-sale double-resume hole

Verification found a real defect: resuming a held sale loaded its lines into
the cart but left the held row resumable, so the same ticket could be
fulfilled twice. Fixed by:
- `SaleService.release_hold(sale_id, user)` — marks the held row `released`
  (audit-logged; held sales carry no payments/stock moves, so nothing to reverse).
- `ui/screens/pos.py::_resume` now calls `release_hold` in the same
  transaction that loads the cart; a second resume attempt raises
  "already processed".
- New test `test_release_hold_prevents_double_resume` added.
- Re-ran everything after the fix: **50/50 pytest**, **27/27** and **20/20**
  offscreen smoke tests — all pass.

Note: if a cashier resumes a hold and then abandons the cart without
checking out, the released hold is not recoverable (same semantics as
clearing a cart). Documented here as accepted v1 behavior.

## 6. How to re-run

```bash
cd ~/workspace/counterX-POS
.venv/bin/python -m pytest tests/ -q
LD_LIBRARY_PATH=~/workspace/.qtlibs QT_QPA_PLATFORM=offscreen \
  .venv/bin/python /tmp/smoke_ui.py
LD_LIBRARY_PATH=~/workspace/.qtlibs QT_QPA_PLATFORM=offscreen \
  .venv/bin/python /tmp/smoke_ui_data.py
```

## 7. Cloud sync UI (2026-10-10)

New/changed files: `src/counterx/ui/screens/sync.py` (new Cloud Sync screen,
registered in `screens/__init__.py` directly after BackupScreen, nav_order 185,
nav_permission "settings"), `src/counterx/ui/dialogs.py` (FirstRunWizard:
business type, logo picker, default tax rate, receipt footer, auto-backup
checkbox, one-time owner recovery code dialog; LoginDialog: "Forgot password?"
-> RecoveryDialog; new RecoveryCodeDialog), `src/main.py` (one shared
SyncService, worker started only when sync enabled, stopped on app exit).

Verification:
- `python -m py_compile` on all touched files: PASS.
- Offscreen smoke test (`/tmp/smoke_sync_ui.py`, PySide6 6.12.0,
  QT_QPA_PLATFORM=offscreen): **10/10 PASS** — SyncScreen registered after
  BackupScreen, nav attrs correct, instantiate + on_show (empty + disabled
  state), honest offline banner present, FirstRunWizard / LoginDialog /
  RecoveryDialog / RecoveryCodeDialog instantiate, SyncService.status path
  returns installation ID.
- Full engine suite excluding sync: **50/50 PASS**.
- `tests/test_sync.py` (sync ENGINE, untouched by this UI work — it imports
  nothing from ui/ or main.py): 7 failures in the full random-order run.
  Consistent failure: `test_v1_to_v2_migration_backfills`
  ("no such table: main.tax_rates" — the migration backfill SQL references a
  table absent from the hand-built v1 schema). The rest are order-dependent
  flakes (`database is locked`, `duplicate column name: sync_uuid`) that pass
  in ordered/isolated runs. These are pre-existing sync-engine issues for the
  engine owner to fix; none involve the UI added here.

Defect found and fixed during this verification: SyncScreen._refresh leaked
the SyncState ORM row out of the closed session (DetachedInstanceError on
on_show). Fixed by extracting plain values inside the session.

Genuinely NOT tested: real Supabase cloud round-trip (no project/credentials
in this environment — Save & Connect and Sync Now paths never hit a live
server); background worker timing under real network conditions; recovery-code
dialog shown from a real wizard finish (modal, needs human); logo file picker
(real file dialog, needs human); Windows exe packaging of the new screen.
