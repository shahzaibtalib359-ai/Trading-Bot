from __future__ import annotations

from backend.config import get_settings

settings = get_settings()

if settings.database_type == "firestore":
    from backend.database.firestore_repository import FirestoreSignalRepository as SignalRepository
else:
    from backend.database.repository import SignalRepository as SignalRepository

__all__ = ["SignalRepository"]
