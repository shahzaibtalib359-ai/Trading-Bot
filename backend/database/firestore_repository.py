from __future__ import annotations

import csv
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from backend.config import get_settings
from backend.models import HistoryRecord, SignalResponse, StatisticsResponse, TradingMode, SignalAction, TradeDuration

logger = logging.getLogger(__name__)


def generate_int_id() -> int:
    """Generate a unique integer ID based on millisecond timestamp and a random offset."""
    return int(time.time() * 1000) * 10 + random.randint(0, 9)


class FirestoreSignalRepository:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._init_firebase()
        self.db = firestore.client()

    def _init_firebase(self) -> None:
        if not firebase_admin._apps:
            # Try to load credentials from JSON string setting (ideal for cloud platforms like Vercel)
            cred_json = self.settings.firebase_credentials_json
            if cred_json:
                import json
                try:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                    return
                except Exception as exc:
                    logger.error("Failed to parse firebase_credentials_json env variable: %s", exc)

            # Fallback to loading credentials from path
            cred_path = self.settings.firebase_credentials_path
            if not cred_path.exists():
                raise FileNotFoundError(
                    f"Firebase credentials JSON not found at {cred_path} and TRADING_FIREBASE_CREDENTIALS_JSON environment variable is not set. "
                    f"Please set the environment variable, save the file on disk, or change TRADING_DATABASE_TYPE to 'sqlite'."
                )
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred)

    def initialize(self) -> None:
        """No schema creation needed for Firestore, but we seed default admin config."""
        self.seed_admin_config()

    def save_signal(self, signal: SignalResponse, user_id: int) -> int:
        signal_id = generate_int_id()
        doc_ref = self.db.collection("signal_history").document(str(signal_id))
        doc_ref.set({
            "id": signal_id,
            "created_at": signal.generated_at.isoformat(),
            "mode": signal.mode.value,
            "pair": signal.pair,
            "signal": signal.signal.value,
            "confidence": signal.confidence,
            "duration": signal.duration.value,
            "market_trend": signal.market_trend,
            "outcome": None,
            "user_id": user_id
        })
        return signal_id

    def list_history(self, user_id: int, limit: int = 100) -> list[HistoryRecord]:
        docs = (
            self.db.collection("signal_history")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .get()
        )
        records = [doc.to_dict() for doc in docs]
        # Sort in memory to avoid requiring composite indexes on Firestore
        records.sort(key=lambda x: x.get("id", 0), reverse=True)
        return [self._history_record(r) for r in records[:limit]]

    def update_outcome(self, signal_id: int, outcome: str, user_id: int) -> None:
        doc_ref = self.db.collection("signal_history").document(str(signal_id))
        doc = doc_ref.get()
        if not doc.exists:
            raise KeyError(f"Signal id {signal_id} was not found.")
        data = doc.to_dict()
        if data.get("user_id") != user_id:
            raise KeyError("Access denied for this signal.")
        doc_ref.update({"outcome": outcome})

    def statistics(self, user_id: int) -> StatisticsResponse:
        docs = (
            self.db.collection("signal_history")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .get()
        )
        total = 0
        wins = 0
        losses = 0
        breakeven = 0
        total_confidence = 0.0

        for doc in docs:
            data = doc.to_dict()
            total += 1
            outcome = data.get("outcome")
            if outcome == "WIN":
                wins += 1
            elif outcome == "LOSS":
                losses += 1
            elif outcome == "BREAKEVEN":
                breakeven += 1
            total_confidence += float(data.get("confidence", 0))

        tracked = wins + losses
        average_confidence = (total_confidence / total) if total > 0 else 0.0

        return StatisticsResponse(
            total_signals=total,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            tracked_win_rate=round((wins / tracked) * 100, 2) if tracked else 0.0,
            average_confidence=round(average_confidence, 2)
        )

    def add_watchlist_pair(self, mode: str, pair: str, user_id: int) -> None:
        # Document ID composite enforces uniqueness per user-mode-pair
        doc_id = f"{user_id}_{mode}_{pair}"
        watchlist_id = generate_int_id()
        doc_ref = self.db.collection("watchlist").document(doc_id)
        doc_ref.set({
            "id": watchlist_id,
            "mode": mode,
            "pair": pair,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id
        }, merge=True)

    def remove_watchlist_pair(self, mode: str, pair: str, user_id: int) -> None:
        doc_id = f"{user_id}_{mode}_{pair}"
        self.db.collection("watchlist").document(doc_id).delete()

    def list_watchlist(self, user_id: int) -> list[dict[str, str]]:
        docs = (
            self.db.collection("watchlist")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .get()
        )
        pairs = []
        for doc in docs:
            data = doc.to_dict()
            pairs.append({
                "mode": data.get("mode", ""),
                "pair": data.get("pair", "")
            })
        pairs.sort(key=lambda x: x.get("pair", ""))
        return pairs

    def export_history_csv(self, output_path: Path, user_id: int) -> Path:
        records = self.list_history(user_id=user_id, limit=10_000)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["Date", "Time", "Mode", "Pair", "Signal", "Confidence", "Duration", "Trend", "Outcome"]
            )
            for record in records:
                writer.writerow(
                    [
                        record.created_at.date().isoformat(),
                        record.created_at.time().isoformat(timespec="seconds"),
                        record.mode.value,
                        record.pair,
                        record.signal.value,
                        record.confidence,
                        record.duration.value,
                        record.market_trend,
                        record.outcome or "",
                    ]
                )
        return output_path

    # ── License CRUD ─────────────────────────────────────────────────────

    def seed_admin_config(self, default_password: str = "07862433") -> None:
        # Check password hash doc
        pw_doc = self.db.collection("admin_config").document("admin_password_hash").get()
        if not pw_doc.exists:
            from backend.database.repository import hash_password
            hashed = hash_password(default_password)
            self.db.collection("admin_config").document("admin_password_hash").set({"value": hashed})

        rec_doc = self.db.collection("admin_config").document("admin_recovery_key_hash").get()
        if not rec_doc.exists:
            import secrets
            from backend.database.repository import hash_password
            recovery_key = f"sb_recovery_{secrets.token_hex(8)}"
            hashed_rec = hash_password(recovery_key)
            self.db.collection("admin_config").document("admin_recovery_key_hash").set({"value": hashed_rec})
            
            print("\n" + "="*70)
            print("ADMIN SECURITY SETUP (FIRESTORE):")
            print(f"SECRET RECOVERY KEY GENERATED: {recovery_key}")
            print("SAVE THIS KEY! Use it to reset the admin password if forgotten.")
            print("="*70 + "\n")

    def get_admin_password_hash(self) -> str | None:
        doc = self.db.collection("admin_config").document("admin_password_hash").get()
        return doc.get("value") if doc.exists else None

    def get_admin_recovery_key_hash(self) -> str | None:
        doc = self.db.collection("admin_config").document("admin_recovery_key_hash").get()
        return doc.get("value") if doc.exists else None

    def set_admin_password_hash(self, new_hash: str) -> None:
        self.db.collection("admin_config").document("admin_password_hash").set({"value": new_hash})

    def insert_license(self, key: str, owner: str, expires_at: str, is_active: int = 1) -> int:
        license_id = generate_int_id()
        self.db.collection("licenses").document(key).set({
            "id": license_id,
            "key": key,
            "owner": owner,
            "device_id": None,
            "activated_at": None,
            "expires_at": expires_at,
            "is_active": is_active,
            "last_activity": None,
            "app_version": None
        })
        return license_id

    def list_licenses(self) -> list[dict]:
        docs = self.db.collection("licenses").get()
        licenses = [doc.to_dict() for doc in docs]
        licenses.sort(key=lambda x: x.get("id", 0), reverse=True)
        return licenses

    def get_license_by_key(self, key: str) -> dict | None:
        doc = self.db.collection("licenses").document(key).get()
        return doc.to_dict() if doc.exists else None

    def activate_license(self, key: str, device_id: str, app_version: str = "") -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("licenses").document(key)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        doc_ref.update({
            "device_id": device_id,
            "activated_at": now,
            "last_activity": now,
            "app_version": app_version
        })
        return doc_ref.get().to_dict()

    def update_license_status(self, key: str, is_active: int) -> bool:
        doc_ref = self.db.collection("licenses").document(key)
        if not doc_ref.get().exists:
            return False
        doc_ref.update({"is_active": is_active})
        return True

    def extend_license(self, key: str, new_expires_at: str) -> bool:
        doc_ref = self.db.collection("licenses").document(key)
        if not doc_ref.get().exists:
            return False
        doc_ref.update({"expires_at": new_expires_at})
        return True

    def delete_license(self, key: str) -> bool:
        doc_ref = self.db.collection("licenses").document(key)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        return True

    def update_license_activity(self, key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("licenses").document(key)
        if doc_ref.get().exists:
            doc_ref.update({"last_activity": now})

    # ── User CRUD ────────────────────────────────────────────────────────

    def insert_user(self, username: str, email: str, password_hash: str) -> int:
        user_id = generate_int_id()
        created_at = datetime.now(timezone.utc).isoformat()
        sub_expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        doc_ref = self.db.collection("users").document(str(user_id))
        doc_ref.set({
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": password_hash,
            "created_at": created_at,
            "is_active": 1,
            "role": "user",
            "subscription_tier": "premium",
            "subscription_expires_at": sub_expires
        })
        return user_id

    def get_user_by_username(self, username: str) -> dict | None:
        docs = (
            self.db.collection("users")
            .where(filter=FieldFilter("username", "==", username))
            .limit(1)
            .get()
        )
        for doc in docs:
            return doc.to_dict()
        return None

    def get_user_by_id(self, user_id: int) -> dict | None:
        doc = self.db.collection("users").document(str(user_id)).get()
        return doc.to_dict() if doc.exists else None

    def list_users(self) -> list[dict]:
        docs = self.db.collection("users").get()
        users = []
        for doc in docs:
            data = doc.to_dict()
            users.append({
                "id": data.get("id"),
                "username": data.get("username"),
                "email": data.get("email"),
                "created_at": data.get("created_at"),
                "is_active": data.get("is_active"),
                "role": data.get("role"),
                "subscription_tier": data.get("subscription_tier"),
                "subscription_expires_at": data.get("subscription_expires_at"),
            })
        users.sort(key=lambda x: x.get("id", 0), reverse=True)
        return users

    def update_user_status(self, user_id: int, is_active: int) -> bool:
        doc_ref = self.db.collection("users").document(str(user_id))
        if not doc_ref.get().exists:
            return False
        doc_ref.update({"is_active": is_active})
        return True

    def admin_update_user_subscription(self, user_id: int, subscription_tier: str, subscription_expires_at: str | None) -> bool:
        doc_ref = self.db.collection("users").document(str(user_id))
        if not doc_ref.get().exists:
            return False
        doc_ref.update({
            "subscription_tier": subscription_tier,
            "subscription_expires_at": subscription_expires_at,
            "is_active": 1
        })
        return True

    # ── API Key CRUD ─────────────────────────────────────────────────────

    def insert_api_key(self, user_id: int, key: str, name: str, expires_at: str | None = None) -> int:
        key_id = generate_int_id()
        created_at = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("api_keys").document(str(key_id))
        doc_ref.set({
            "id": key_id,
            "user_id": user_id,
            "key": key,
            "name": name,
            "created_at": created_at,
            "expires_at": expires_at,
            "is_active": 1,
            "last_activity": None
        })
        return key_id

    def get_api_key_details(self, key: str) -> dict | None:
        docs = (
            self.db.collection("api_keys")
            .where(filter=FieldFilter("key", "==", key))
            .limit(1)
            .get()
        )
        for doc in docs:
            return doc.to_dict()
        return None

    def list_user_api_keys(self, user_id: int) -> list[dict]:
        docs = (
            self.db.collection("api_keys")
            .where(filter=FieldFilter("user_id", "==", user_id))
            .get()
        )
        keys = [doc.to_dict() for doc in docs]
        keys.sort(key=lambda x: x.get("id", 0), reverse=True)
        return keys

    def list_all_api_keys(self) -> list[dict]:
        key_docs = self.db.collection("api_keys").get()
        keys = [doc.to_dict() for doc in key_docs]
        
        user_docs = self.db.collection("users").get()
        users_map = {str(u.get("id")): u.get("username") for u in [doc.to_dict() for doc in user_docs]}
        
        joined_keys = []
        for key in keys:
            uid = str(key.get("user_id"))
            key["username"] = users_map.get(uid, "unknown")
            joined_keys.append(key)
            
        joined_keys.sort(key=lambda x: x.get("id", 0), reverse=True)
        return joined_keys

    def update_api_key_status(self, key: str, is_active: int) -> bool:
        docs = (
            self.db.collection("api_keys")
            .where(filter=FieldFilter("key", "==", key))
            .limit(1)
            .get()
        )
        for doc in docs:
            doc.reference.update({"is_active": is_active})
            return True
        return False

    def delete_api_key(self, key: str) -> bool:
        docs = (
            self.db.collection("api_keys")
            .where(filter=FieldFilter("key", "==", key))
            .limit(1)
            .get()
        )
        for doc in docs:
            doc.reference.delete()
            return True
        return False

    def update_api_key_activity(self, key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        docs = (
            self.db.collection("api_keys")
            .where(filter=FieldFilter("key", "==", key))
            .limit(1)
            .get()
        )
        for doc in docs:
            doc.reference.update({"last_activity": now})

    # ── Security Alerts CRUD ──────────────────────────────────────────────

    def insert_security_alert(self, username: str, email: str, license_key: str | None, device_id: str | None, alert_type: str, details: str) -> int:
        alert_id = generate_int_id()
        now = datetime.now(timezone.utc).isoformat()
        doc_ref = self.db.collection("security_alerts").document(str(alert_id))
        doc_ref.set({
            "id": alert_id,
            "created_at": now,
            "username": username,
            "email": email,
            "license_key": license_key,
            "device_id": device_id,
            "alert_type": alert_type,
            "details": details
        })
        return alert_id

    def list_security_alerts(self, limit: int = 100) -> list[dict]:
        docs = self.db.collection("security_alerts").get()
        alerts = [doc.to_dict() for doc in docs]
        alerts.sort(key=lambda x: x.get("id", 0), reverse=True)
        return alerts[:limit]

    def clear_security_alerts(self) -> None:
        batch = self.db.batch()
        docs = self.db.collection("security_alerts").get()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

    # ── Helper ───────────────────────────────────────────────────────────

    @staticmethod
    def _history_record(data: dict) -> HistoryRecord:
        signal = data.get("signal")
        if signal == "NO TRADE":
            signal = "WAIT"
        elif signal == "BUY / UP":
            signal = "UP"
        elif signal == "SELL / DOWN":
            signal = "DOWN"
        return HistoryRecord(
            id=data.get("id"),
            created_at=datetime.fromisoformat(data.get("created_at")),
            mode=TradingMode(data.get("mode")),
            pair=data.get("pair"),
            signal=SignalAction(signal),
            confidence=data.get("confidence"),
            duration=TradeDuration(data.get("duration")),
            market_trend=data.get("market_trend"),
            outcome=data.get("outcome"),
        )
