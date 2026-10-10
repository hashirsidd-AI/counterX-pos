"""Cloud transports. stdlib only (urllib) — no new dependencies.

Security design (honest):
- Only the Supabase **anon key** is stored in the app. The anon key is public
  by design; all real protection comes from Row Level Security policies that
  scope every row to its installation_id (see documentation/SUPABASE_SETUP.md).
- The **service-role key is NEVER embedded** in the desktop application.
- Per-installation Supabase Auth user (email+random password, generated once)
  gives each business its own identity; RLS ties rows to auth.uid().
- Passwords and password hashes are NEVER uploaded.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol


class SyncError(Exception):
    """Transport-level failure (network, auth, server error). Retryable."""


class CloudTransport(Protocol):
    def upsert(self, table: str, rows: list[dict], *, on_conflict: str,
               merge: bool) -> None:
        """Idempotent write. merge=True -> last-write-wins; False -> first wins."""
        ...

    def check_connection(self) -> bool:
        ...


def _http(method: str, url: str, headers: dict, body: bytes | None,
          timeout: int = 15) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001 - network errors are retryable
        raise SyncError(f"Network error: {e}")


class SupabaseTransport:
    """PostgREST + Auth via the public Supabase HTTP API."""

    def __init__(self, base_url: str, anon_key: str,
                 token_provider) -> None:
        """
        token_provider: zero-arg callable returning a valid JWT access token,
        refreshing it if needed (may raise SyncError).
        """
        self.base_url = base_url.rstrip("/")
        self.anon_key = anon_key
        self._token_provider = token_provider

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self._token_provider()}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def upsert(self, table: str, rows: list[dict], *, on_conflict: str,
               merge: bool) -> None:
        if not rows:
            return
        prefer = ("resolution=merge-duplicates"
                  if merge else "resolution=ignore-duplicates")
        url = (f"{self.base_url}/rest/v1/{table}"
               f"?on_conflict={urllib.parse.quote(on_conflict)}")
        body = json.dumps(rows).encode()
        status, data = _http("POST", url,
                             self._headers({"Prefer": prefer}), body)
        if status in (200, 201, 204):
            return
        raise SyncError(f"Supabase upsert {table} -> HTTP {status}: "
                        f"{data[:200].decode(errors='replace')}")

    def check_connection(self) -> bool:
        url = f"{self.base_url}/rest/v1/"
        try:
            status, _ = _http("GET", url, {"apikey": self.anon_key}, None,
                              timeout=10)
            return status < 500
        except SyncError:
            return False


class SupabaseAuth:
    """Per-installation user management via Supabase Auth (anon key only)."""

    def __init__(self, base_url: str, anon_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.anon_key = anon_key

    def _auth_headers(self) -> dict:
        return {"apikey": self.anon_key, "Content-Type": "application/json"}

    def sign_up(self, email: str, password: str) -> dict:
        url = f"{self.base_url}/auth/v1/signup"
        status, data = _http("POST", url, self._auth_headers(),
                             json.dumps({"email": email,
                                         "password": password}).encode())
        payload = json.loads(data.decode() or "{}")
        if status in (200, 201):
            return payload
        msg = str(payload.get("msg") or payload.get("message") or data[:200])
        if "already registered" in msg.lower() or status in (400, 422):
            raise _AlreadyRegistered(msg)
        raise SyncError(f"Supabase sign-up HTTP {status}: {msg[:200]}")

    def sign_in(self, email: str, password: str) -> dict:
        url = f"{self.base_url}/auth/v1/token?grant_type=password"
        status, data = _http("POST", url, self._auth_headers(),
                             json.dumps({"email": email,
                                         "password": password}).encode())
        if status == 200:
            return json.loads(data.decode())
        raise SyncError(f"Supabase sign-in HTTP {status}: "
                        f"{data[:200].decode(errors='replace')}")

    def refresh(self, refresh_token: str) -> dict:
        url = f"{self.base_url}/auth/v1/token?grant_type=refresh_token"
        status, data = _http("POST", url, self._auth_headers(),
                             json.dumps({"refresh_token": refresh_token}).encode())
        if status == 200:
            return json.loads(data.decode())
        raise SyncError("Supabase token refresh failed")


class _AlreadyRegistered(Exception):
    pass


class FakeTransport:
    """In-memory cloud for tests. Records every upsert; can be told to fail."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict]] = {}  # table -> sync_uuid -> row
        self.fail_next: int = 0
        self.calls: list[tuple] = []

    def upsert(self, table: str, rows: list[dict], *, on_conflict: str,
               merge: bool) -> None:
        self.calls.append((table, len(rows), merge))
        if self.fail_next > 0:
            self.fail_next -= 1
            raise SyncError("simulated transport failure")
        store = self.tables.setdefault(table, {})
        for row in rows:
            key = row[on_conflict]
            if key in store and not merge:
                continue  # ignore-duplicates: first write wins
            store[key] = row

    def check_connection(self) -> bool:
        return self.fail_next == 0
