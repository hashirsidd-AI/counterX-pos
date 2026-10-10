"""Offline-first cloud sync (optional Supabase).

Local SQLite is always the system of record. Mutations write to a local
outbox table (sync_queue) in the SAME transaction; a background worker
uploads rows when connectivity allows. Billing never waits for the cloud.
"""
from .service import SyncService, SyncResult
from .transport import CloudTransport, SupabaseTransport, FakeTransport, SyncError

__all__ = ["SyncService", "SyncResult", "CloudTransport",
           "SupabaseTransport", "FakeTransport", "SyncError"]
