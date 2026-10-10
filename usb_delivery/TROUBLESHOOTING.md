# counterX POS — Troubleshooting Guide

Work through the list below before calling support. Most problems are solved in under five minutes.

## App won't start

1. Wait 30 seconds and try again — the first start after installation is slower.
2. Restart the computer, then open the app again.
3. If your antivirus shows a warning, allow **counterX POS**. Some antivirus programs block new software by mistake.
4. If it still won't open, re-run **counterX-POS-Setup-1.0.0.exe** from the USB stick (this repairs the installation without touching your data).

## Login problems

- **Wrong username or password:** check that **Caps Lock** is off. Passwords are case-sensitive.
- **Forgot the owner password:** another owner account can reset it in **Employees & Permissions**. If there is only one owner and the password is lost, contact counterX support — do not delete any files trying to fix this yourself.
- **"Account disabled":** the owner has deactivated this user. Ask the owner to re-enable it.

## "Permission denied" messages

This is not an error — it means your user role is not allowed to do that action (for example, a cashier trying to give a discount or void a sale). Ask an owner or manager to do it, or to change your permissions in **Employees & Permissions**.

## Printer not printing

1. Check the printer is switched **on**, has **paper**, and shows no error lights.
2. In Windows, print a test page to confirm the printer itself works.
3. In counterX POS, open **Printer Settings** and make sure the correct printer is selected for receipts (and a separate one for the kitchen, if you use one). Click **Test Print**.
4. If printing fails, the app keeps your sale safe and offers to save the receipt as a file instead — you can print that file later.
5. **Note:** physical receipt-printer testing was not done as part of this release. If your printer model behaves oddly, tell support the exact printer brand and model.

## Barcode scanner types into the wrong place (or not at all)

1. A barcode scanner works like a keyboard. Click inside the **search box** on the **New Sale** screen first, then scan.
2. After scanning, the app expects the **Enter** key. Most scanners can be set to send Enter after each scan — check your scanner's manual for "suffix Enter".
3. Make sure the product's barcode is saved correctly in **Products & Menu**.

## Totals look wrong

1. Check the quantity on each cart line (**+ Qty** / **− Qty**).
2. Check whether a discount was applied (item discount or order discount).
3. Check the tax rate in **Business Settings**. Tax is configurable — if the rate is wrong there, every bill will be wrong. Set it to what your business actually uses.

## Shift won't close

1. You must type the **counted cash** before closing — the button stays disabled until then.
2. Only an owner or manager can close a shift. A cashier will see "permission denied".
3. If a checkout was left half-finished, complete or cancel it on the **New Sale** screen first.

## Database errors / "database is locked"

1. Close the app fully and open it again.
2. Never delete, rename, or move files inside `%APPDATA%\counterX`. That folder is your business data.
3. If the error repeats, restore your latest backup (see **BACKUP_RESTORE_GUIDE.md**).

## The app froze

1. Wait one minute — it may be finishing a print or backup.
2. If it stays frozen, close it with **Alt+F4** or Task Manager and reopen it. Held sales and completed sales are saved, so you will not lose them.

## Before calling support, collect this

1. The **exact message** on the screen (take a photo with your phone).
2. What you were doing when it happened (which screen, which button).
3. Your app version: open **License & About** — it shows the version number.
4. The log files, found in `%APPDATA%\counterX\logs` — support may ask you to send the newest one.

## Where things live

| What | Location |
|---|---|
| Database | `%APPDATA%\counterX\data\counterx.db` |
| Backups | `%APPDATA%\counterX\backups` |
| Logs | `%APPDATA%\counterX\logs` |
| Saved receipts | `%APPDATA%\counterX\receipts` |

(For example: `C:\Users\YourName\AppData\Roaming\counterX\backups`)

## Support

**counterX** — Phone: +92 315 7988387 | +44 7878 921068

When you call, keep the shop computer switched on and the app open if possible.
