# counterX POS — Backup & Restore Guide

## Why backups matter

Your database holds **everything**: every sale, product, shift, and report. If the computer's hard disk fails or Windows is reinstalled, the database can be lost. A backup is a dated copy of that database that lets you get everything back.

**Rule: keep at least one backup copy outside the shop computer** (for example, on the counterX USB stick or a second USB drive kept at home).

## 1. Manual backup (do this now)

1. Open **Database & Backup** from the sidebar.
2. Click **Backup Now**.
3. Wait for the success message. The app checks the backup file before reporting success — if the message says the backup completed, the file is valid.
4. The backup appears in the list with its **date and time**.

Do a manual backup at the end of every business day for the first few weeks, until automatic backup is confirmed working.

## 2. Automatic backup

1. Open **Database & Backup**.
2. Switch on **Automatic backup**.
3. Choose how often it runs (daily is recommended).

The computer must be switched on at the scheduled time. If the shop PC is off overnight, set the schedule for a time when it is on, or rely on the manual end-of-day backup.

## 3. Copy a backup to a USB drive

1. Open **Database & Backup**.
2. Click **Open Backup Folder**.
3. Copy the newest backup file (its name contains the date and time) to your USB stick.
4. Keep that USB stick somewhere safe — not next to the computer.

Tip: rotate two USB sticks (one at the shop, one at home) so you always have a recent copy off-site.

## 4. Restore from a backup

Read this whole section before restoring.

**Warning: restoring REPLACES your current database with the backup.** Any sales made after that backup was taken will be gone from the app. To protect you, the app automatically takes a **safety backup** of your current data before every restore — so nothing is destroyed silently.

Steps:

1. Open **Database & Backup**.
2. Select the backup you want from the list (check the date and time carefully).
3. Click **Restore Selected**.
4. Read the warning message and confirm.
5. The app validates the backup, takes a safety backup of the current data, then restores.
6. **Restart the app** when it tells you to.
7. After restarting, check the **Dashboard** — the figures should match the date of the backup you restored.

If anything looks wrong after a restore, the safety backup (listed with the current date) can be restored the same way to get back to where you started.

## 5. How to verify a backup

- In **Database & Backup**, every listed backup shows its date, size, and validation status. The app validates integrity automatically when the backup is created.
- A healthy backup file is never 0 KB. If a backup shows 0 KB or "invalid", delete it and take a fresh one with **Backup Now**.
- Once a month, copy a backup to a different computer with counterX POS installed and restore it there as a test. This proves your backups actually work.

## Quick reference

| Task | Where |
|---|---|
| Take a backup now | Database & Backup → **Backup Now** |
| Turn on auto backup | Database & Backup → **Automatic backup** |
| Find backup files | Database & Backup → **Open Backup Folder** |
| Restore | Database & Backup → select backup → **Restore Selected** |

## Support

**counterX** — Phone: +92 315 7988387 | +44 7878 921068
