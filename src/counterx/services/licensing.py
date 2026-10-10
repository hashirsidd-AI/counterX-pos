"""Offline commercial licensing.

Basic offline scheme (documented honestly in the user manual):
- A license key is HMAC-signed with a vendor secret; the app verifies it
  locally, so normal billing never needs the internet.
- Trade-offs: like any offline check, a determined user with a debugger can
  bypass it. It stops casual copying and gives each client an identity,
  an expiry, and a paper trail — it is not DRM.

Key format: CX1-<base32(payload)><base32(signature[:10])>
payload = issued_to | valid_until | nonce   (valid_until empty = perpetual)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import date

from sqlalchemy.orm import Session

from .. import models

# NOTE: This is a demo vendor secret. Before commercial distribution, replace
# it with a per-vendor secret generated offline and kept private.
_VENDOR_SECRET = b"counterx-demo-vendor-secret-change-before-sale"


def _b32e(data: bytes) -> str:
    return base64.b32encode(data).decode().rstrip("=")


def _b32d(data: str) -> bytes:
    return base64.b32decode(data + "=" * (-len(data) % 8))


def issue_key(issued_to: str, valid_until: str = "") -> str:
    """Vendor-side helper (run offline by counterX when selling a license)."""
    payload = f"{issued_to}|{valid_until}".encode()
    sig = hmac.new(_VENDOR_SECRET, b"CX1" + payload, hashlib.sha256).digest()[:10]
    return f"CX1-{_b32e(payload + sig)}"


def verify_key(key: str) -> dict | None:
    try:
        key = key.strip().upper()
        if not key.startswith("CX1-"):
            return None
        raw = _b32d(key[4:])
        payload, sig = raw[:-10], raw[-10:]
        expect = hmac.new(_VENDOR_SECRET, b"CX1" + payload, hashlib.sha256).digest()[:10]
        if not hmac.compare_digest(sig, expect):
            return None
        issued_to, valid_until = payload.decode().split("|", 1)
        return {"issued_to": issued_to, "valid_until": valid_until}
    except Exception:  # noqa: BLE001
        return None


class LicenseService:
    def __init__(self, session: Session):
        self.s = session

    def status(self) -> dict:
        lic = (self.s.query(models.License).order_by(models.License.id.desc()).first())
        if not lic:
            return {"state": "unlicensed", "issued_to": "", "valid_until": ""}
        info = verify_key(lic.license_key)
        if not info:
            return {"state": "invalid", "issued_to": "", "valid_until": ""}
        if info["valid_until"]:
            expired = info["valid_until"] < date.today().isoformat()
            state = "expired" if expired else "active"
        else:
            state = "active"
        return {"state": state, "issued_to": info["issued_to"],
                "valid_until": info["valid_until"], "key": lic.license_key}

    def activate(self, key: str) -> dict:
        info = verify_key(key)
        if not info:
            raise ValueError("Invalid license key")
        self.s.query(models.License).delete()
        self.s.add(models.License(license_key=key.strip().upper(),
                                  issued_to=info["issued_to"],
                                  valid_until=info["valid_until"]))
        self.s.flush()
        return self.status()
