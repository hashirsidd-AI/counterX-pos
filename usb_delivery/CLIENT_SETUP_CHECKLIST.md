# counterX POS — Client Deployment Checklist

**For the counterX team.** Complete every item when installing at a new client site. Tick each box before leaving.

## 1. Business details

- [ ] Business name, address, city, and phone number entered in **Business Settings**.
- [ ] Business logo added (appears on reports/receipts where supported).
- [ ] Receipt footer text configured (for example: "Thank you for shopping with us!").
- [ ] Opening hours recorded.

## 2. Tax configuration

- [ ] Tax rates created in **Business Settings** matching the client's actual requirements.
- [ ] Default tax rate set correctly (or set to 0% if the client does not charge tax).
- [ ] Tax registration details entered if the client has them.

> **Important — no compliance claim:** counterX POS records whatever tax rates you configure. It does **not** certify FBR, SRB, PRA, or any other tax-authority compliance. The client (or their accountant) must verify which rates, invoice fields, and registration details their business legally requires. Do not promise compliance to the client.

## 3. Users and roles

- [ ] Owner account created; password handed to the business owner privately.
- [ ] Manager account(s) created with the correct role.
- [ ] Cashier account(s) created with the correct role.
- [ ] Permissions reviewed in **Employees & Permissions** (who can discount, refund, void, adjust stock, close shifts).
- [ ] Each staff member tested their own login.

## 4. Products, categories, and opening stock

- [ ] Categories created in **Categories & Modifiers**.
- [ ] Products created in **Products & Menu** with correct names (English/Urdu), selling prices, and barcodes/SKUs.
- [ ] Opening stock quantities entered in **Inventory & Stock**.
- [ ] A test product search by name **and** by barcode works on the **New Sale** screen.

## 5. Payment methods

- [ ] Cash workflow confirmed (tendered/change).
- [ ] Card / bank-transfer methods enabled if the client uses them.

## 6. Printers

- [ ] Receipt printer selected in **Printer Settings**; **test print** successful.
- [ ] Kitchen printer selected and test-printed (restaurants).
- [ ] Receipt layout checked: business name, invoice number, date/time, items, totals, tax, footer all present.

> **Note:** physical receipt-printer testing was not done during development. Test thoroughly on the client's actual printer model and record the model here: _______________

## 7. Backup

- [ ] First manual backup taken (**Database & Backup → Backup Now**) and verified in the list.
- [ ] Automatic backup switched on with a sensible schedule.
- [ ] Backup copied to the client's USB drive; client shown where backups live.

## 8. End-to-end test sale

- [ ] Open a shift with opening cash.
- [ ] Make a test sale (cash), print the receipt.
- [ ] Record a test expense, then close the shift and check expected vs. counted cash.
- [ ] Void the test transactions if the client wants a clean start, or leave them clearly marked as tests.

## 9. Staff training (15–20 minutes)

- [ ] Cashier: login, **New Sale**, checkout, hold/resume, reprint receipt.
- [ ] Cashier: **Cash Register** (cash in/out, expenses).
- [ ] Manager: **Shift Management** open/close, **Reports & Analytics**, refunds/voids.
- [ ] Owner: **Employees & Permissions**, **Database & Backup**, **License & About**.

## 10. License

- [ ] License key activated in **License & About** (status shows **Active**).
- [ ] Client informed about the license terms (see **LICENSE_INFO.md**).

## 11. Handover

- [ ] Owner has the USB stick with the installer and these guides.
- [ ] Owner knows the support numbers: **+92 315 7988387** | **+44 7878 921068**.
- [ ] Client name, install date, and PC details recorded by the counterX team:

Client: ______________________ Date: __________ PC/User: ______________________
