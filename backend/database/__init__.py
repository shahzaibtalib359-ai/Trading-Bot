from backend.config import get_settings

settings = get_settings()

print("=" * 60)
print("DATABASE TYPE =", settings.database_type)
print("=" * 60)

if settings.database_type.lower() == "firestore":
    print("USING FIRESTORE REPOSITORY")
    from .firestore_repository import FirestoreSignalRepository as SignalRepository
else:
    print("USING SQLITE REPOSITORY")
    from .repository import SignalRepository

__all__ = ["SignalRepository"]
