from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LICENSE_DIR = ROOT / "desktop" / "licenses"
SESSION_FILE = LICENSE_DIR / "session.json"


@dataclass(frozen=True)
class SessionStatus:
    valid: bool
    message: str
    username: str = ""
    user_id: str = ""
    session_token: str = ""
    api_key: str = ""


class LicenseManager:
    """
    Manages session and API Key state on the desktop client.
    
    Caches credentials locally inside licenses/session.json so subsequent launches
    don't require re-logging in.
    """

    def __init__(self, session_file: Path = SESSION_FILE) -> None:
        self.session_file = session_file
        self.session_file.parent.mkdir(parents=True, exist_ok=True)

    def validate(self) -> SessionStatus:
        """Check the locally cached session file."""
        if not self.session_file.exists():
            return SessionStatus(False, "Login required. Sign in or Sign up to access.")
        try:
            payload = json.loads(self.session_file.read_text(encoding="utf-8"))
            username = payload.get("username", "")
            user_id = str(payload.get("user_id", ""))
            session_token = payload.get("session_token", "")
            api_key = payload.get("api_key", "")

            if not session_token or not user_id or not api_key:
                return SessionStatus(False, "Session incomplete. Please login again.")

            return SessionStatus(
                valid=True,
                message="Session active.",
                username=username,
                user_id=user_id,
                session_token=session_token,
                api_key=api_key
            )
        except Exception as exc:
            logger.warning("Session validation error: %s", exc)
            return SessionStatus(False, "Session could not be validated.")

    def get_stored_credentials(self) -> tuple[str, str, str]:
        """Return (api_key, user_id, session_token) from local cache, or empty strings."""
        if not self.session_file.exists():
            return "", "", ""
        try:
            payload = json.loads(self.session_file.read_text(encoding="utf-8"))
            return (
                payload.get("api_key", ""),
                str(payload.get("user_id", "")),
                payload.get("session_token", "")
            )
        except Exception:
            return "", "", ""

    def save_session(self, username: str, user_id: int, session_token: str, api_key: str) -> None:
        """Persist session credentials locally."""
        payload = {
            "username": username,
            "user_id": user_id,
            "session_token": session_token,
            "api_key": api_key
        }
        self.session_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def clear(self) -> None:
        """Remove stored session."""
        if self.session_file.exists():
            self.session_file.unlink()
