# counterX POS — Professional Offline POS for Pakistan

Native Windows desktop Point of Sale application for Pakistani restaurants,
cafes, bakeries, retail and general stores. Offline-first: the database lives
on the shop's own computer, and daily billing never needs the internet.

**Company:** counterX — +92 315 7988387, +44 7878 921068

## Tech stack

| Layer      | Technology |
|------------|------------|
| Language   | Python 3.10+ |
| UI         | PySide6 (native Qt desktop, no browser) |
| Database   | SQLite (WAL mode, foreign keys enforced) |
| ORM        | SQLAlchemy 2.x + versioned migrations |
| Packaging  | PyInstaller (exe) + Inno Setup (installer) |
| Money      | `Decimal`, 2 dp, HALF_UP everywhere |

## Project layout

```
counterX-POS/
  src/
    main.py                 # application entry point
    counterx/
      config.py             # paths, theme, Pakistan defaults, roles/permissions
      database.py           # engine, sessions, migrations, seed
      models.py             # SQLAlchemy schema
      security.py           # PBKDF2 password hashing
      services/             # business logic (auth, sales, inventory, shifts,
                            #   catalog, reports, backup, licensing, printing)
      ui/                   # PySide6 screens (navy/teal/white theme)
      utils/                # money, validators
  tests/                    # pytest suite (40 tests, all passing on Linux)
  installer/                # counterx.spec, counterx.iss, build_windows.bat
  documentation/            # video analysis, manuals, guides
  usb_delivery/             # final USB package contents
```

## Development quickstart (any OS)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
```

## Building the Windows installer (Windows 10/11 64-bit only)

```bat
installer\build_windows.bat
```

This is honest about one limitation: **the `.exe` and the Setup installer can
only be built and tested on a real Windows machine.** This Linux environment
produces the complete source, the PyInstaller spec, the Inno Setup script and
the one-click build script — but the final `counterX-POS-Setup-1.0.0.exe` must
be generated on Windows. Nothing here claims otherwise.

## Optional cloud sync (offline-first)

Local SQLite is always the system of record. An optional Supabase
integration uploads records in the background when online (outbox pattern,
idempotent, retrying). Billing never waits for the cloud. See
`documentation/SUPABASE_SETUP.md`. No service-role key is embedded in the
app; each installation is isolated by its own ID via Row Level Security.

## Key design decisions

- **Offline by default.** No server, no cloud, no license phone-home for billing.
- **Permissions enforced in services**, not just by hiding buttons.
- **Idempotent checkout** (`client_ref`): double-clicks and retries can never
  create a duplicate sale.
- **Cash drawer math**: only cash payments, cash in/out, cash expenses and cash
  refunds affect expected cash. Card/bank transfers never do.
- **Backups are validated** (integrity check + sha256) before success is reported;
  restore always takes a safety backup first.
- **Migrations** preserve customer data across upgrades; uninstall never deletes
  the database.
