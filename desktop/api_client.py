from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)


@dataclass
class ApiClient:
    base_url: str = os.getenv("TRADING_API_BASE_URL", "http://127.0.0.1:8012/api")
    timeout: int = 8
    api_key: str = ""
    user_id: str = ""
    user_token: str = ""
    _admin_token: str = field(default="", repr=False)

    @staticmethod
    def _backend_mode(mode: str) -> str:
        if mode == "Binance Spot":
            return "Crypto"
        return mode

    # ── Config ────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        return self._request("GET", "/config")

    # ── Signals ───────────────────────────────────────────────────────

    def generate_signal(self, mode: str, pair: str, duration: str, source_url: str | None = None) -> dict:
        mode = self._backend_mode(mode)
        payload = {"mode": mode, "pair": pair, "duration": duration}
        if source_url:
            payload["source_url"] = source_url
        return self._request(
            "POST",
            "/signals/generate",
            json=payload,
        )

    def scan_pairs(self, mode: str, duration: str, pairs: list[str] | None = None) -> list[dict]:
        if pairs:
            return [
                self.generate_signal(mode, pair, duration)
                for pair in pairs
            ]
        mode = self._backend_mode(mode)
        return self._request("POST", "/signals/scan", params={"mode": mode, "duration": duration})

    def refresh_market_data(
        self,
        mode: str,
        pair: str,
        duration: str,
        source_url: str | None = None,
    ) -> dict:
        mode = self._backend_mode(mode)
        payload = {"mode": mode, "pair": pair, "duration": duration}
        if source_url:
            payload["source_url"] = source_url
        return self._request("POST", "/market-data/refresh", json=payload)

    # ── History & statistics ──────────────────────────────────────────

    def history(self, limit: int = 100) -> list[dict]:
        return self._request("GET", "/history", params={"limit": limit})

    def statistics(self) -> dict:
        return self._request("GET", "/statistics")

    def update_outcome(self, signal_id: int, outcome: str) -> dict:
        return self._request("PATCH", f"/history/{signal_id}/outcome", json={"outcome": outcome})

    # ── User authentication ───────────────────────────────────────────

    def user_register(self, username: str, email: str, password: str) -> dict:
        return self._request(
            "POST", "/auth/register",
            json={"username": username, "email": email, "password": password}
        )

    def user_login(self, username: str, password: str) -> dict:
        result = self._request(
            "POST", "/auth/login",
            json={"username": username, "password": password}
        )
        self.user_token = result.get("token", "")
        self.user_id = str(result.get("user_id", ""))
        return result

    def user_logout(self) -> None:
        self.user_token = ""
        self.user_id = ""
        self.api_key = ""

    # ── User API Key management ───────────────────────────────────────

    def user_get_keys(self) -> list[dict]:
        return self._request("GET", "/user/keys")

    def user_create_key(self, name: str = "Desktop Client Key", days: int | None = None) -> dict:
        payload = {"name": name}
        if days is not None:
            payload["days"] = days
        return self._request("POST", "/user/keys", json=payload)

    def user_revoke_key(self, key: str) -> dict:
        return self._request("DELETE", f"/user/keys/{key}")

    def get_user_profile(self) -> dict:
        return self._request("GET", "/user/profile")

    # ── Admin authentication ──────────────────────────────────────────

    def admin_login(self, password: str) -> dict:
        result = self._request("POST", "/admin/login", json={"password": password})
        self._admin_token = result.get("token", "")
        return result

    def admin_logout(self) -> None:
        self._admin_token = ""

    @property
    def is_admin_logged_in(self) -> bool:
        return bool(self._admin_token)

    # ── Admin user & API key management ───────────────────────────────

    def admin_list_users(self) -> list[dict]:
        return self._request("GET", "/admin/users")

    def admin_update_user_status(self, user_id: int, is_active: bool) -> dict:
        return self._request(
            "PATCH", f"/admin/users/{user_id}/status",
            json={"is_active": is_active}
        )

    def admin_update_user_subscription(self, user_id: int, tier: str, expires_at: str | None) -> dict:
        return self._request(
            "PATCH", f"/admin/users/{user_id}/subscription",
            json={"subscription_tier": tier, "subscription_expires_at": expires_at}
        )

    def admin_list_keys(self) -> list[dict]:
        return self._request("GET", "/admin/keys")

    def admin_update_key_status(self, key: str, is_active: bool) -> dict:
        return self._request(
            "PATCH", f"/admin/keys/{key}/status",
            json={"is_active": is_active}
        )

    def admin_delete_key(self, key: str) -> dict:
        return self._request("DELETE", f"/user/keys/{key}")

    def admin_change_password(self, current_password: str, new_password: str) -> dict:
        return self._request(
            "POST", "/admin/change-password",
            params={"current_password": current_password, "new_password": new_password},
        )

    # ── Core request method ───────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> dict | list[dict]:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        
        # Include API key and user ID if available for signal/watchlist endpoints
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.user_id:
            headers["X-User-Id"] = self.user_id
            
        # Include user token if available (for key management)
        if self.user_token:
            headers["X-User-Token"] = self.user_token
            
        # Include admin token if available
        if self._admin_token:
            headers["X-Admin-Token"] = self._admin_token
            
        try:
            response = requests.request(method, url, timeout=self.timeout, headers=headers, **kwargs)
            if response.status_code >= 400:
                try:
                    detail = response.json().get("detail", response.text)
                except ValueError:
                    detail = response.text
                raise RuntimeError(str(detail))
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, RuntimeError):
            logger.exception("API request failed: %s %s", method, url)
            raise
