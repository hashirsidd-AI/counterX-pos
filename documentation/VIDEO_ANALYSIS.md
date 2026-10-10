# Reference Video Analysis — counterX POS

Date analyzed: 2026-10-10
Source: Google Drive screen recording (Bandicam), ~9 minutes, recorded 30 Jan 2025 ~15:27–15:36
Subject: "IndoIj" restaurant POS demo at demo.indoljpos.pk/dashboard (a web-based restaurant POS used as a workflow reference only — we are building a native Windows desktop app, not a website)

## What is genuinely visible in the video (verified frame by frame)

### 1. Dashboard
- Module cards: Work Periods, Point Of Sale, Order Histories
- Toast notification: "Work period has been ended"
- Clock display with date/time; footer "© Powered By IndoIj || All Rights Reserved"

### 2. POS billing screen
- Left panel: searchable category list — Chocolate, Platters, Spaghetti, CHICKEN (Chinese), Beef (Chinese), STARTERS (Chinese), SPICY WOK NOODELS, SOUPS (Chinese), STARTER, BURGERS - BEEF KOUZINA, BURGERS - CHICKEN KOUZINA; "WEB MENU" dropdown; search box
- Order-type buttons: ONLINE ODR, DINE-IN, DELIVERY, TAKEAWAY, SETTLED, RUNNING ODR.; plus a FOOD PANDA (aggregator) button and grid-view toggle
- Item cards with photos and names: Chinese Platter, Fried Food Platter, Cibus Kung Pao, Sweet & Sour Chicken, Chicken Manchurian
- Bill panel: Business Day (30-01-2025), TOKEN # (e.g. U8-1, U8-3), order-type header (Dine-In – Dine-In / Takeaway – Takeaway), item rows with qty +/- steppers and price, SubTotal, Tax (15%) dropdown, Del Charge, S.C. (service charge), Dis (discount), Offers dropdown (e.g. "10% Off"), Total Bill
- Action buttons: BACK, HOLD, SYNC, SETTLE, SUBMIT
- Per-item strikethrough pricing when an offer applies (e.g. Sweet & Sour Chicken Rs964.80, struck Rs1072)

### 3. Kitchen order ticket (KOT)
- Printed ticket layout: TOKEN NO - U8-1, INVOICE NO - 350, "Kitchen Orders (Kitc)", Dine-In, Ref No, Table #: Table 2, Waiter Name: Waiter 2
- Itemized Qty / Item grouped by category (CHICKEN (Chinese), Platters), date + time
- Routed through the OS print dialog (Save as PDF in the demo)

### 4. Settle / payment screen
- "Settle Order (Table: Table 2)", order token U8-1, full item table (S/L, Food, Additional Info/Properties, QTY)
- Total: 8291.50 | Tip: 0.000 | Paid Amount: 10000
- Denomination keypad: 10, 20, 50, 100, 500, 1000, 5000, All, 0, C, Settle
- Payment buttons: GO BACK, CASH, CARD, SPLIT PAYMENT

### 5. Takeaway order with discount (worked example)
- TOKEN # U8-3: Sweet & Sour Chicken ×1, Cibus Kung Pao ×1
- 10% Off offer → Dis 228.70; SubTotal Rs2287.00; Tax (15%) Rs343.05; Total Bill Rs2401.35

### 6. Shift close report
- SHIFT REPORT / DEMO / SHIFT CLOSE with Report Date, Terminal (Demo), Open Date (30-01-2025 03:27:53), Close Date, User
- SALES DETAILS: Sales Variance 0.00, Gross Sales 9,497.00, Free Of Cost 0.00, Discount 228.70, Cancelled 0.00, Refund 0.00, Net Sales 9,268.30, Tax Amount 1,424.55, Net Sales Including Tax 10,692.85, Delivery Charges 0.00, Service Charges 0.00, Department Commission 0.00, Total Collected 0.00→(printed), Pos Service Fee 0.00, Order Tip 0.00
- INSIGHT: Number Of Orders 2, Number Of Customers 2
- PAYMENT WISE SALES: Cash 10693 / Total 10,692.85
- ORDER TYPE SALES: Dine-In ×1 → 8,291.50; Takeaway ×1 → 2,401.35; Total 10,692.85
- Exported via OS print dialog → PDF

### 7. Order history
- Table: S/L, Token, Invoice No, Branch (Demo), Total Bill, Status, Time, Date, User Name
- Statuses seen: Ready, Processing, Cancelled
- Filters: From date / To date (calendar picker), search by token, customer dropdown, FILTER button, ONLINE ORDERS button

### 8. Contextual clues
- Recorder's browser bookmarks include "Restaurant POS by I…", "POS Users", and "SRB POS Portal" (SRB = Sindh Revenue Board — Pakistani tax-portal context)
- Multi-terminal concept visible ("Terminal: Demo"), per-user attribution ("User")

## Feature checklist derived from the video (only verified items)

1. Work-period (shift/day) open & close with business-day tracking
2. Dashboard with module navigation cards
3. POS billing: category tree, text search, photo item cards
4. Order types: Dine-In, Takeaway, Delivery, Online orders; SETTLED / RUNNING ODR. views
5. Token numbers per order + sequential invoice numbers
6. Table and waiter assignment for dine-in
7. Cart: qty steppers, item rows, per-item offer pricing (strikethrough)
8. Tax (configurable rate), service charge, delivery charge, order-level discounts/offers
9. Order actions: Back, Hold/Resume (implied), Sync, Settle, Submit
10. Kitchen order ticket printing (token, invoice, table, waiter, itemized)
11. Settlement screen: total, paid amount, tip, denomination keypad, Cash / Card / Split payment, change-due logic (implied)
12. Third-party aggregator entry point (Food Panda button)
13. Shift-close report: sales details, payment-wise sales, order-type sales, insights; PDF export
14. Order history with status tracking (Ready/Processing/Cancelled) and date/token/customer filters
15. Multi-terminal + per-user attribution

## Explicitly NOT verifiable from the video (do not claim these were seen)

- Barcode scanning, SKU management, stock/inventory deduction or alerts
- User roles, permissions, login security
- Refunds/returns flow, void authorization
- Backup/restore, database technology
- Customer database details, loyalty
- Expenses, suppliers, purchases
- Urdu text or RTL rendering
- Receipt printer hardware integration (only OS print dialog shown)
- Offline behavior

These are covered separately by the project requirements where specified.
