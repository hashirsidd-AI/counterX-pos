# counterX POS — Changelog v1.1.0

Release focus: easier daily workflow, professional CounterX branding, a
better dashboard, and a ready-to-use sample menu. No database schema
changes; v1.0.0 databases upgrade in place without data loss.

## Simplified workflow
- New streamlined **Add/Edit Product** dialog: name, category (+ inline
  "new category" button), sell price, cost price, stock quantity,
  low-stock alert, barcode, and image on the main form; SKU, Urdu name,
  tax rate, stock tracking, and description moved under an expandable
  **Advanced Options** section.
- Auto-generated unique SKUs (`P-00001` …) for new products.
- Editing a product shows current stock; changing the quantity posts a
  labelled stock adjustment.
- Suppliers stay optional — nothing forces supplier setup before the
  first sale.

## Demo fast-food menu
- First-run wizard offers **"Load sample fast-food menu (recommended)"**
  or **"Start with empty catalogue"**.
- 6 categories / 21 items (Burgers, Pizza, Roasted & Grilled,
  Fries & Sides, Cold Drinks, Extras) with sensible sample prices and
  opening stock, all clearly marked `DEMO-` and editable.
- Seeding is idempotent: never duplicates, never touches real products.
- Products screen shows a demo banner with one-click **Remove demo data**.

## POS billing screen
- Categories are now a horizontal scrollable button row ("All" + each
  category) with the active category highlighted.
- Taller product cards (name + price); out-of-stock items show "(Out)".
- Table / Waiter / Service charge / Delivery charge collapsed into a
  toggleable **Order details** section; sale type, customer, and notes
  stay visible.
- Larger Checkout button and grand total. Cart, totals, hold/resume,
  KOT, discounts, and checkout logic unchanged.

## Dashboard
- Header with business name, date, shift status, and logged-in user.
- Six KPI cards: Today's Sales, Orders, Avg Order Value, Cash in Shift,
  Low-Stock Items, Held Orders.
- Real-data 7-day sales bar chart and a Recent Transactions table.
- Professional empty state with **Create Your First Sale** when no sale
  exists yet. Payment Breakdown, Order Types, Top Products, Current
  Shift, and Low Stock panels kept.

## Branding
- New wordmark: **◆ CounterX** + "POS SOFTWARE COMPANY" on the sidebar,
  login screen, and installer; "Powered by CounterX" added to receipts.
- Sidebar navigation grouped: SALES / CATALOG / CASH / MANAGE / SYSTEM.

## Technical
- `APP_VERSION` 1.1.0 (build 110); installer
  `counterX-POS-Setup-1.1.0.exe`.
- New: `CatalogService.generate_sku()`, `services/demo_data.py`
  (`seed_demo_menu`, `remove_demo_data`).
- New tests: `tests/test_demo_data.py` (4), `tests/test_ui_smoke_110.py`
  (offscreen GUI smoke). All 63 pre-existing tests still pass.
- Supabase sync, licensing, backup/restore, permissions, and offline
  billing unchanged.
