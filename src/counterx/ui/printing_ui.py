"""Bridging PrintService text output to real printers.

Strategy (honest, no fake success):
- Windows + win32print importable + a printer configured -> send raw text
  to that printer, report the real result.
- Otherwise -> save the text to the receipts folder and tell the user
  exactly where it went. The saved sale is NEVER at risk: printing is a
  separate step after checkout and can always be retried from Order History.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from ..config import RECEIPT_DIR

log = logging.getLogger("counterx.printing_ui")


def save_text_file(text: str, prefix: str) -> Path:
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RECEIPT_DIR / f"{prefix}_{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def list_printers() -> list[str]:
    """Printer names visible to the OS. Empty list = none found / unsupported."""
    if sys.platform.startswith("win"):
        try:
            import win32print  # type: ignore
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            return [p[2] for p in win32print.EnumPrinters(flags)]
        except Exception:  # noqa: BLE001
            log.exception("win32print enumeration failed")
            return []
    return []


def print_text(text: str, printer_name: str = "") -> tuple[bool, str]:
    """Send raw text to a Windows printer. Returns (ok, message)."""
    if not sys.platform.startswith("win"):
        path = save_text_file(text, "print")
        return False, ("Direct printing is available on the Windows build. "
                       f"Text saved to {path}")
    try:
        import win32print  # type: ignore
    except ImportError:
        path = save_text_file(text, "print")
        return False, ("win32print is not installed on this machine. "
                       f"Text saved to {path}")
    try:
        name = printer_name or win32print.GetDefaultPrinter()
        handle = win32print.OpenPrinter(name)
        try:
            job = win32print.StartDocPrinter(handle, 1, ("counterX print", None, "RAW"))
            try:
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, text.encode("utf-8", errors="replace"))
                win32print.EndPagePrinter(handle)
            finally:
                win32print.EndDocPrinter(handle)
        finally:
            win32print.ClosePrinter(handle)
        return True, f"Sent to printer '{name}' (job {job})"
    except Exception as e:  # noqa: BLE001
        log.exception("win32print failed")
        path = save_text_file(text, "print")
        return False, f"Printer error ({e}). Text saved to {path} — retry anytime."
