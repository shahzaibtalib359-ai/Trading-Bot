from backend.config import get_settings

settings = get_settings()

if settings.database_type.lower() == "firestore":
    from .firestore_repository import FirestoreSignalRepository as SignalRepository
else:
    from .repository import SignalRepository

__all__ = ["SignalRepository"]
