from __future__ import annotations

import csv
import hashlib
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator

from backend.config import get_settings
from backend.models import HistoryRecord, SignalResponse, StatisticsResponse


def hash_password(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{hashed.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, hashed_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hashed_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    mode TEXT NOT NULL,
    pair TEXT NOT NULL,
    signal TEXT NOT NULL,
    confidence INTEGER NOT NULL,
    duration TEXT NOT NULL,
    market_trend TEXT NOT NULL,
    outcome TEXT,
    user_id INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    pair TEXT NOT NULL,
    created_at TEXT NOT NULL,
    user_id INTEGER DEFAULT 1,
    UNIQUE(mode, pair, user_id)
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    owner TEXT NOT NULL,
    device_id TEXT,
    activated_at TEXT,
    expires_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    last_activity TEXT,
    app_version TEXT
);

CREATE TABLE IF NOT EXISTS admin_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    username TEXT NOT NULL,
    email TEXT NOT NULL,
    license_key TEXT,
    device_id TEXT,
    alert_type TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    role TEXT DEFAULT 'user',
    subscription_tier TEXT DEFAULT 'premium',
    subscription_expires_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    is_active INTEGER DEFAULT 1,
    last_activity TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


class SignalRepository:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or get_settings().database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        self.seed_admin_config()
        self._run_migrations()

    def _run_migrations(self) -> None:
        """Run all incremental schema migrations safely."""
        with self.connect() as connection:
            # 1. Add user_id to signal_history if missing
            try:
                connection.execute("ALTER TABLE signal_history ADD COLUMN user_id INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass

            # 2. Add user_id column to watchlist if missing (before constraint migration)
            try:
                connection.execute("ALTER TABLE watchlist ADD COLUMN user_id INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass

            # 3. Users role
            try:
                connection.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
            except sqlite3.OperationalError:
                pass

            # 4. Users subscription_tier
            try:
                connection.execute("ALTER TABLE users ADD COLUMN subscription_tier TEXT DEFAULT 'premium'")
            except sqlite3.OperationalError:
                pass

            # 5. Users subscription_expires_at
            try:
                connection.execute("ALTER TABLE users ADD COLUMN subscription_expires_at TEXT")
            except sqlite3.OperationalError:
                pass

            # 7. Create security_alerts table if missing
            try:
                connection.execute("""
                CREATE TABLE IF NOT EXISTS security_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    username TEXT NOT NULL,
                    email TEXT NOT NULL,
                    license_key TEXT,
                    device_id TEXT,
                    alert_type TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                """)
            except sqlite3.OperationalError:
                pass

        # 6. Migrate watchlist UNIQUE constraint from (mode, pair) -> (mode, pair, user_id)
        #    Required for multi-tenant isolation: the old unique constraint blocked different
        #    users from adding the same trading pair (INSERT OR IGNORE silently discarded rows).
        self._migrate_watchlist_constraint()

    def _migrate_watchlist_constraint(self) -> None:
        """Recreate the watchlist table with UNIQUE(mode, pair, user_id) if needed."""
        with self.connect() as connection:
            # Check existing unique indexes on watchlist
            indexes = connection.execute("PRAGMA index_list(watchlist)").fetchall()
            needs_migration = True
            for idx in indexes:
                idx_name = idx["name"]
                idx_info = connection.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
                idx_cols = {row["name"] for row in idx_info}
                # If an index already covers (mode, pair, user_id), we're good
                if idx_cols == {"mode", "pair", "user_id"}:
                    needs_migration = False
                    break

            if not needs_migration:
                return

            # Recreate with correct composite unique key
            connection.executescript("""
                PRAGMA foreign_keys=OFF;
                CREATE TABLE IF NOT EXISTS watchlist_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    user_id INTEGER DEFAULT 1,
                    UNIQUE(mode, pair, user_id)
                );
                INSERT OR IGNORE INTO watchlist_new (id, mode, pair, created_at, user_id)
                    SELECT id, mode, pair, created_at, COALESCE(user_id, 1) FROM watchlist;
                DROP TABLE watchlist;
                ALTER TABLE watchlist_new RENAME TO watchlist;
                PRAGMA foreign_keys=ON;
            """)

    def save_signal(self, signal: SignalResponse, user_id: int) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO signal_history
                (created_at, mode, pair, signal, confidence, duration, market_trend, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.generated_at.isoformat(),
                    signal.mode.value,
                    signal.pair,
                    signal.signal.value,
                    signal.confidence,
                    signal.duration.value,
                    signal.market_trend,
                    user_id,
                ),
            )
            return int(cursor.lastrowid)

    def list_history(self, user_id: int, limit: int = 100) -> list[HistoryRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM signal_history WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
            ).fetchall()
        return [self._history_record(row) for row in rows]

    def update_outcome(self, signal_id: int, outcome: str, user_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE signal_history SET outcome = ? WHERE id = ? AND user_id = ?",
                (outcome, signal_id, user_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Signal id {signal_id} was not found or access denied.")

    def statistics(self, user_id: int) -> StatisticsResponse:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) AS losses,
                    SUM(CASE WHEN outcome = 'BREAKEVEN' THEN 1 ELSE 0 END) AS breakeven,
                    AVG(confidence) AS average_confidence
                FROM signal_history
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        breakeven = int(row["breakeven"] or 0)
        tracked = wins + losses
        return StatisticsResponse(
            total_signals=int(row["total"] or 0),
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            tracked_win_rate=round((wins / tracked) * 100, 2) if tracked else 0.0,
            average_confidence=round(float(row["average_confidence"] or 0), 2),
        )

    def add_watchlist_pair(self, mode: str, pair: str, user_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO watchlist(mode, pair, created_at, user_id) VALUES (?, ?, ?, ?)",
                (mode, pair, datetime.now(timezone.utc).isoformat(), user_id),
            )

    def remove_watchlist_pair(self, mode: str, pair: str, user_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM watchlist WHERE mode = ? AND pair = ? AND user_id = ?",
                (mode, pair, user_id),
            )

    def list_watchlist(self, user_id: int) -> list[dict[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT mode, pair FROM watchlist WHERE user_id = ? ORDER BY pair", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

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
        """Seed the admin_config table with a hashed default password and recovery key if missing."""
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT value FROM admin_config WHERE key = 'admin_password_hash'"
            ).fetchone()
            if existing is None:
                hashed = hash_password(default_password)
                connection.execute(
                    "INSERT INTO admin_config(key, value) VALUES (?, ?)",
                    ("admin_password_hash", hashed),
                )
            
            existing_rec = connection.execute(
                "SELECT value FROM admin_config WHERE key = 'admin_recovery_key_hash'"
            ).fetchone()
            if existing_rec is None:
                recovery_key = f"sb_recovery_{secrets.token_hex(8)}"
                hashed_rec = hash_password(recovery_key)
                connection.execute(
                    "INSERT INTO admin_config(key, value) VALUES (?, ?)",
                    ("admin_recovery_key_hash", hashed_rec),
                )
                
                print("\n" + "="*70)
                print("ADMIN SECURITY SETUP:")
                print(f"SECRET RECOVERY KEY GENERATED: {recovery_key}")
                print("SAVE THIS KEY! Use it to reset the admin password if forgotten.")
                print("="*70 + "\n")

    def get_admin_password_hash(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM admin_config WHERE key = 'admin_password_hash'"
            ).fetchone()
        return row["value"] if row else None

    def get_admin_recovery_key_hash(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM admin_config WHERE key = 'admin_recovery_key_hash'"
            ).fetchone()
        return row["value"] if row else None

    def set_admin_password_hash(self, new_hash: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO admin_config(key, value) VALUES (?, ?)",
                ("admin_password_hash", new_hash),
            )

    def insert_license(
        self,
        key: str,
        owner: str,
        expires_at: str,
        is_active: int = 1,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO licenses (key, owner, expires_at, is_active)
                VALUES (?, ?, ?, ?)
                """,
                (key, owner, expires_at, is_active),
            )
            return int(cursor.lastrowid)

    def list_licenses(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM licenses ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_license_by_key(self, key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM licenses WHERE key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def activate_license(
        self, key: str, device_id: str, app_version: str = ""
    ) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE licenses
                SET device_id = ?, activated_at = ?, last_activity = ?, app_version = ?
                WHERE key = ?
                """,
                (device_id, now, now, app_version, key),
            )
            row = connection.execute(
                "SELECT * FROM licenses WHERE key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def update_license_status(self, key: str, is_active: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE licenses SET is_active = ? WHERE key = ?",
                (is_active, key),
            )
            return cursor.rowcount > 0

    def extend_license(self, key: str, new_expires_at: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE licenses SET expires_at = ? WHERE key = ?",
                (new_expires_at, key),
            )
            return cursor.rowcount > 0

    def delete_license(self, key: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM licenses WHERE key = ?", (key,)
            )
            return cursor.rowcount > 0

    def update_license_activity(self, key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                "UPDATE licenses SET last_activity = ? WHERE key = ?",
                (now, key),
            )

    # ── User CRUD ────────────────────────────────────────────────────────

    def insert_user(self, username: str, email: str, password_hash: str) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        # Default subscriptions to 30 days from signup
        sub_expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (username, email, password_hash, created_at, role, subscription_tier, subscription_expires_at)
                VALUES (?, ?, ?, ?, 'user', 'premium', ?)
                """,
                (username, email, password_hash, created_at, sub_expires),
            )
            return int(cursor.lastrowid)

    def get_user_by_username(self, username: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, username, email, created_at, is_active, role, subscription_tier, subscription_expires_at FROM users ORDER BY id DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_user_status(self, user_id: int, is_active: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET is_active = ? WHERE id = ?",
                (is_active, user_id),
            )
            return cursor.rowcount > 0

    def admin_update_user_subscription(self, user_id: int, subscription_tier: str, subscription_expires_at: str | None) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET subscription_tier = ?, subscription_expires_at = ?, is_active = 1 WHERE id = ?",
                (subscription_tier, subscription_expires_at, user_id),
            )
            return cursor.rowcount > 0

    # ── API Key CRUD ─────────────────────────────────────────────────────

    def insert_api_key(self, user_id: int, key: str, name: str, expires_at: str | None = None) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO api_keys (user_id, key, name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, key, name, created_at, expires_at),
            )
            return int(cursor.lastrowid)

    def get_api_key_details(self, key: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM api_keys WHERE key = ?", (key,)
            ).fetchone()
        return dict(row) if row else None

    def list_user_api_keys(self, user_id: int) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM api_keys WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_all_api_keys(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT k.*, u.username 
                FROM api_keys k 
                JOIN users u ON k.user_id = u.id 
                ORDER BY k.id DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def update_api_key_status(self, key: str, is_active: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET is_active = ? WHERE key = ?",
                (is_active, key),
            )
            return cursor.rowcount > 0

    def delete_api_key(self, key: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM api_keys WHERE key = ?", (key,)
            )
            return cursor.rowcount > 0

    def update_api_key_activity(self, key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                "UPDATE api_keys SET last_activity = ? WHERE key = ?",
                (now, key),
            )

    # ── Security Alerts CRUD ──────────────────────────────────────────────

    def insert_security_alert(self, username: str, email: str, license_key: str | None, device_id: str | None, alert_type: str, details: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO security_alerts (created_at, username, email, license_key, device_id, alert_type, details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (now, username, email, license_key, device_id, alert_type, details)
            )
            return int(cursor.lastrowid)

    def list_security_alerts(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM security_alerts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_security_alerts(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM security_alerts")

    # ── History helpers ──────────────────────────────────────────────────

    @staticmethod
    def _history_record(row: sqlite3.Row) -> HistoryRecord:
        signal = row["signal"]
        if signal == "NO TRADE":
            signal = "WAIT"
        elif signal == "BUY / UP":
            signal = "UP"
        elif signal == "SELL / DOWN":
            signal = "DOWN"
        return HistoryRecord(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            mode=row["mode"],
            pair=row["pair"],
            signal=signal,
            confidence=row["confidence"],
            duration=row["duration"],
            market_trend=row["market_trend"],
            outcome=row["outcome"],
        )
