from __future__ import annotations

import logging
import secrets
import time
import jwt
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import BASE_DIR
from backend.constants import BINANCE_SPOT_PAIRS, CRYPTO_PAIRS, FOREX_PAIRS, QUOTEX_PAIRS, SUPPORTED_DURATIONS
from backend.database import SignalRepository
from backend.database.repository import hash_password, verify_password
from backend.models import (
    HistoryRecord,
    MarketDataRefreshResponse,
    OutcomeUpdate,
    SignalAction,
    SignalRequest,
    SignalResponse,
    StatisticsResponse,
    TradingMode,
)
from backend.signal_manager import signal_manager
logger = logging.getLogger(__name__)
router = APIRouter()

JWT_SECRET = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_123456789"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 12



# ── In-memory admin session store ────────────────────────────────────

_admin_sessions: dict[str, datetime] = {}
_SESSION_TTL = timedelta(hours=4)


def _cleanup_sessions() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _admin_sessions.items() if now - v > _SESSION_TTL]
    for k in expired:
        _admin_sessions.pop(k, None)


# ── In-memory user session store ─────────────────────────────────────

_user_sessions: dict[str, tuple[int, datetime]] = {}  # token -> (user_id, login_time)
_USER_SESSION_TTL = timedelta(days=7)


def _cleanup_user_sessions() -> None:
    now = datetime.now(timezone.utc)
    expired = [k for k, v in _user_sessions.items() if now - v[1] > _USER_SESSION_TTL]
    for k in expired:
        _user_sessions.pop(k, None)


# ── Online user heartbeat tracking ───────────────────────────────────
# Maps user_id -> last heartbeat timestamp (epoch seconds)
_online_heartbeats: dict[int, float] = {}
_ONLINE_TIMEOUT = 300  # 5 minutes


def _mark_user_online(user_id: int) -> None:
    _online_heartbeats[user_id] = time.time()


def _count_online_users() -> int:
    cutoff = time.time() - _ONLINE_TIMEOUT
    return sum(1 for ts in _online_heartbeats.values() if ts > cutoff)


# ── Dependencies ─────────────────────────────────────────────────────


def get_repository() -> SignalRepository:
    return SignalRepository()


def validate_pair(mode: TradingMode, pair: str) -> None:
    if mode == TradingMode.forex:
        allowed = FOREX_PAIRS
    elif mode == TradingMode.crypto:
        allowed = CRYPTO_PAIRS + BINANCE_SPOT_PAIRS
    else:
        allowed = QUOTEX_PAIRS
    if pair not in allowed:
        raise HTTPException(status_code=400, detail=f"{pair} is not available for {mode.value}.")


async def verify_api_key_access(
    x_api_key: str = Header(default=""),
    x_user_id: str = Header(default=""),
    x_user_token: str = Header(default=""),
    repository: SignalRepository = Depends(get_repository),
) -> dict:
    """
    Dependency that validates access via either:
    1. A valid user session token (x_user_token)
    2. A valid API key and User ID (x_api_key and x_user_id)
    Returns a dict containing 'user_id' so dependent endpoints function identically.
    """
    if x_user_token:
        _cleanup_user_sessions()
        if x_user_token not in _user_sessions:
            raise HTTPException(status_code=401, detail="User session invalid or expired.")
        user_id, _ = _user_sessions[x_user_token]
        user = repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=403, detail="User account not found.")
        
        if user.get("subscription_expires_at"):
            sub_expires = datetime.fromisoformat(user["subscription_expires_at"])
            if sub_expires.tzinfo is None:
                sub_expires = sub_expires.replace(tzinfo=timezone.utc)
            if sub_expires <= datetime.now(timezone.utc):
                repository.update_user_status(user_id, 0)
                raise HTTPException(status_code=403, detail="User subscription has expired.")
                
        if not user.get("is_active"):
            raise HTTPException(status_code=403, detail="User account suspended.")
        return {"user_id": user_id, "email": user["email"], "is_active": user["is_active"]}

    if not x_api_key or not x_user_id:
        raise HTTPException(status_code=401, detail="API key and user id are required.")
    try:
        user_id_int = int(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user id format.")

    key_details = repository.get_api_key_details(x_api_key)
    if key_details is None:
        raise HTTPException(status_code=403, detail="API Key not found.")
    
    if key_details["user_id"] != user_id_int:
        raise HTTPException(status_code=403, detail="API Key does not belong to this user.")
        
    if not key_details.get("is_active"):
        raise HTTPException(status_code=403, detail="API Key has been disabled by admin.")
        
    if key_details.get("expires_at"):
        expires_at = datetime.fromisoformat(key_details["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="API Key expired.")
            
    # Also verify the user is active and subscription not expired
    user = repository.get_user_by_id(user_id_int)
    if user is None:
        raise HTTPException(status_code=403, detail="User account not found.")
        
    if user.get("subscription_expires_at"):
        sub_expires = datetime.fromisoformat(user["subscription_expires_at"])
        if sub_expires.tzinfo is None:
            sub_expires = sub_expires.replace(tzinfo=timezone.utc)
        if sub_expires <= datetime.now(timezone.utc):
            repository.update_user_status(user_id_int, 0)
            raise HTTPException(status_code=403, detail="User subscription has expired.")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account has been suspended.")
        
    repository.update_api_key_activity(x_api_key)
    return key_details


async def verify_user_token(
    x_user_token: str = Header(default=""),
    repository: SignalRepository = Depends(get_repository),
) -> int:
    """Dependency that validates user token and returns user_id."""
    _cleanup_user_sessions()
    if not x_user_token or x_user_token not in _user_sessions:
        raise HTTPException(status_code=401, detail="User authentication required.")
    user_id, _ = _user_sessions[x_user_token]
    user = repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=403, detail="User account not found.")
        
    if user.get("subscription_expires_at"):
        sub_expires = datetime.fromisoformat(user["subscription_expires_at"])
        if sub_expires.tzinfo is None:
            sub_expires = sub_expires.replace(tzinfo=timezone.utc)
        if sub_expires <= datetime.now(timezone.utc):
            repository.update_user_status(user_id, 0)
            raise HTTPException(status_code=403, detail="User subscription has expired.")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account suspended.")
    return user_id


async def verify_admin_token(
    x_admin_token: str = Header(default=""),
) -> str:
    if not x_admin_token:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication required."
        )

    try:
        payload = jwt.decode(
            x_admin_token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )

        if payload.get("type") != "admin":
            raise HTTPException(
                status_code=401,
                detail="Invalid admin token."
            )

        return x_admin_token

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Admin token expired."
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token."
        )

# ── Pydantic request/response models ─────────────────────────────────


class AdminLoginRequest(BaseModel):
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    message: str


class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class UserLoginRequest(BaseModel):
    username: str
    password: str


class UserLoginResponse(BaseModel):
    token: str
    user_id: int
    username: str
    email: str


class CreateApiKeyRequest(BaseModel):
    name: str = "Desktop Client Key"
    days: int | None = None


class CreateApiKeyResponse(BaseModel):
    key: str
    name: str
    created_at: str
    expires_at: str | None


class UserStatusUpdate(BaseModel):
    is_active: bool


class ApiKeyStatusUpdate(BaseModel):
    is_active: bool


# ── Public endpoints ─────────────────────────────────────────────────


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config")
async def app_config() -> dict[str, list[str] | dict[str, list[str]]]:
    return {
        "modes": [TradingMode.crypto.value, "Binance Spot", TradingMode.quotex.value, TradingMode.forex.value],
        "pairs": {
            "Crypto": CRYPTO_PAIRS,
            "Binance Spot": BINANCE_SPOT_PAIRS,
            "Quotex": QUOTEX_PAIRS,
            "Forex": FOREX_PAIRS,
        },
        "durations": SUPPORTED_DURATIONS,
    }


# ── Protected signal endpoints ───────────────────────────────────────


@router.post("/signals/generate", response_model=SignalResponse)
async def generate_signal(
    request: SignalRequest,
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> SignalResponse:
    validate_pair(request.mode, request.pair)
    user_id = api_key_details["user_id"]
    try:
        signal = await signal_manager.generate(request)
        if signal.signal.value != "WAIT":
            repository.save_signal(signal, user_id=user_id)
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Market analysis failed.") from exc
    except Exception as exc:
        logger.exception("Signal generation failed")
        raise HTTPException(status_code=502, detail=str(exc) or "Market analysis failed.") from exc


@router.post("/signals/scan", response_model=list[SignalResponse])
async def scan_pairs(
    mode: TradingMode,
    duration: str = Query("15 Seconds"),
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> list[SignalResponse]:
    user_id = api_key_details["user_id"]
    if mode == TradingMode.forex:
        pairs = FOREX_PAIRS
    elif mode == TradingMode.crypto:
        pairs = CRYPTO_PAIRS + BINANCE_SPOT_PAIRS
    else:
        pairs = QUOTEX_PAIRS
    results: list[SignalResponse] = []
    for pair in pairs:
        request = SignalRequest(mode=mode, pair=pair, duration=duration)
        signal = await signal_manager.generate(request)
        if signal.signal.value != "WAIT":
            repository.save_signal(signal, user_id=user_id)
        results.append(signal)
    return sorted(results, key=lambda item: item.confidence, reverse=True)


@router.post("/signals/scan-quotex", response_model=list[SignalResponse])
async def scan_quotex_pairs(
    duration: str = Query("1 Minute"),
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> list[SignalResponse]:
    """Scan all Quotex OTC pairs quickly and return only UP/DOWN signals sorted by confidence."""
    import asyncio
    from backend.services.market_data import is_forex_market_open
    user_id = api_key_details["user_id"]
    
    # Prioritize OTC pairs (most traded on Quotex)
    otc_pairs = [p for p in QUOTEX_PAIRS if "OTC" in p]
    
    results: list[SignalResponse] = []
    errors: list[str] = []

    async def _scan_one(pair: str) -> SignalResponse | None:
        try:
            request = SignalRequest(mode=TradingMode.quotex, pair=pair, duration=duration)
            signal = await signal_manager.generate(request)
            if signal.signal.value != "WAIT":
                repository.save_signal(signal, user_id=user_id)
            return signal
        except Exception as exc:
            err_str = str(exc).lower()
            if "closed" in err_str or "weekend" in err_str or "after-hours" in err_str:
                return SignalResponse(
                    mode=TradingMode.quotex,
                    pair=pair,
                    current_price=0.0,
                    signal=SignalAction.wait,
                    confidence=0,
                    duration=duration,
                    market_trend="Market Closed",
                    status="MARKET_CLOSED",
                    analysis=["🔴 Market Closed — Forex market is closed on weekends."],
                    data_warning="Market is closed (weekend/after-hours).",
                )
            errors.append(f"{pair}: {exc}")
            return None

    # Run pairs concurrently in small batches to avoid rate limits
    batch_size = 5
    for i in range(0, len(otc_pairs), batch_size):
        batch = otc_pairs[i:i + batch_size]
        batch_results = await asyncio.gather(*[_scan_one(p) for p in batch], return_exceptions=False)
        for r in batch_results:
            if r is not None:
                results.append(r)

    # Return only actionable UP/DOWN signals, sorted by confidence desc
    actionable = [r for r in results if r.signal.value != "WAIT" and r.status != "MARKET_CLOSED"]
    actionable_sorted = sorted(actionable, key=lambda r: r.confidence, reverse=True)
    
    # If no actionable signals found, return top 5 WAIT signals with explanation
    if not actionable_sorted:
        all_sorted = sorted(results, key=lambda r: r.confidence, reverse=True)
        return all_sorted[:5]
    
    return actionable_sorted


# ── Admin Signal Endpoints (use admin token, no API key needed) ──────

@router.post("/admin/signal/generate", response_model=SignalResponse)
async def admin_generate_signal(
    request: SignalRequest,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> SignalResponse:
    """Admin can generate signals directly without API key."""
    # Validate pair for the mode
    if request.mode == TradingMode.forex:
        allowed = FOREX_PAIRS
    elif request.mode == TradingMode.crypto:
        allowed = CRYPTO_PAIRS + BINANCE_SPOT_PAIRS
    else:
        allowed = QUOTEX_PAIRS
    if request.pair not in allowed:
        raise HTTPException(status_code=400, detail=f"{request.pair} is not available for {request.mode.value}.")
    try:
        signal = await signal_manager.generate(request)
        # Save with admin user_id=1 (or first user)
        if signal.signal.value != "WAIT":
            try:
                repository.save_signal(signal, user_id=1)
            except Exception:
                pass  # Don't fail if save fails
        return signal
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Market analysis failed.") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Market analysis failed.") from exc


@router.post("/admin/signal/scan-quotex", response_model=list[SignalResponse])
async def admin_scan_quotex(
    duration: str = Query("1 Minute"),
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[SignalResponse]:
    """Admin scan all Quotex OTC pairs."""
    import asyncio
    from backend.services.market_data import is_forex_market_open
    otc_pairs = [p for p in QUOTEX_PAIRS if "OTC" in p]
    results: list[SignalResponse] = []
    market_open = is_forex_market_open()

    async def _scan_one(pair: str) -> SignalResponse | None:
        try:
            req = SignalRequest(mode=TradingMode.quotex, pair=pair, duration=duration)
            sig = await signal_manager.generate(req)
            if sig.signal.value != "WAIT":
                try:
                    repository.save_signal(sig, user_id=1)
                except Exception:
                    pass
            return sig
        except Exception as exc:
            err_str = str(exc).lower()
            if "closed" in err_str or "weekend" in err_str or "after-hours" in err_str:
                # Return a special MARKET_CLOSED response instead of None
                return SignalResponse(
                    mode=TradingMode.quotex,
                    pair=pair,
                    current_price=0.0,
                    signal=SignalAction.wait,
                    confidence=0,
                    duration=duration,
                    market_trend="Market Closed",
                    status="MARKET_CLOSED",
                    analysis=["🔴 Market Closed — Forex market is closed on weekends. Reopens Sunday ~22:00 UTC."],
                    data_warning="Market is closed (weekend/after-hours). OTC pairs are unavailable.",
                )
            return None

    batch_size = 5
    for i in range(0, len(otc_pairs), batch_size):
        batch = otc_pairs[i:i + batch_size]
        batch_results = await asyncio.gather(*[_scan_one(p) for p in batch])
        for r in batch_results:
            if r is not None:
                results.append(r)

    actionable = [r for r in results if r.signal.value != "WAIT" and r.status != "MARKET_CLOSED"]
    if not actionable:
        return sorted(results, key=lambda r: r.confidence, reverse=True)[:5]
    return sorted(actionable, key=lambda r: r.confidence, reverse=True)


@router.post("/admin/signal/scan", response_model=list[SignalResponse])
async def admin_scan_pairs(
    mode: TradingMode,
    duration: str = Query("1 Minute"),
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[SignalResponse]:
    """Admin scan all pairs for a given mode."""
    import asyncio
    if mode == TradingMode.forex:
        pairs = FOREX_PAIRS
    elif mode == TradingMode.crypto:
        pairs = CRYPTO_PAIRS + BINANCE_SPOT_PAIRS
    else:
        pairs = QUOTEX_PAIRS

    results: list[SignalResponse] = []

    async def _scan_one(pair: str) -> SignalResponse | None:
        try:
            req = SignalRequest(mode=mode, pair=pair, duration=duration)
            sig = await signal_manager.generate(req)
            return sig
        except Exception:
            return None

    batch_size = 4
    for i in range(0, len(pairs), batch_size):
        batch = pairs[i:i + batch_size]
        batch_results = await asyncio.gather(*[_scan_one(p) for p in batch])
        for r in batch_results:
            if r is not None:
                results.append(r)

    actionable = [r for r in results if r.signal.value != "WAIT"]
    if not actionable:
        return sorted(results, key=lambda r: r.confidence, reverse=True)[:5]
    return sorted(actionable, key=lambda r: r.confidence, reverse=True)


@router.post("/market-data/refresh", response_model=MarketDataRefreshResponse)
async def refresh_market_data(
    request: SignalRequest,
    _api_key: dict = Depends(verify_api_key_access),
) -> MarketDataRefreshResponse:
    validate_pair(request.mode, request.pair)
    try:
        snapshot = await signal_manager.data_engine.snapshot(request)
        return MarketDataRefreshResponse(
            mode=request.mode,
            pair=request.pair,
            current_price=round(snapshot.latest_price, 5),
            data_source=snapshot.data_source,
            last_market_update=snapshot.latest_update,
            status="LIVE",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Market refresh failed.") from exc


# ── History & statistics (protected) ─────────────────────────────────


@router.get("/history", response_model=list[HistoryRecord])
async def history(
    limit: int = Query(100, ge=1, le=1000),
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> list[HistoryRecord]:
    user_id = api_key_details["user_id"]
    return repository.list_history(user_id=user_id, limit=limit)


@router.patch("/history/{signal_id}/outcome")
async def update_outcome(
    signal_id: int,
    update: OutcomeUpdate,
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> dict[str, str]:
    user_id = api_key_details["user_id"]
    try:
        repository.update_outcome(signal_id, update.outcome, user_id=user_id)
        return {"status": "updated"}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/statistics", response_model=StatisticsResponse)
async def statistics(
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> StatisticsResponse:
    user_id = api_key_details["user_id"]
    return repository.statistics(user_id=user_id)


@router.get("/watchlist")
async def watchlist(
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> list[dict[str, str]]:
    user_id = api_key_details["user_id"]
    return repository.list_watchlist(user_id=user_id)


@router.post("/watchlist")
async def add_watchlist(
    request: SignalRequest,
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> dict[str, str]:
    validate_pair(request.mode, request.pair)
    user_id = api_key_details["user_id"]
    repository.add_watchlist_pair(request.mode.value, request.pair, user_id=user_id)
    return {"status": "added"}


@router.delete("/watchlist")
async def remove_watchlist(
    mode: TradingMode,
    pair: str,
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> dict[str, str]:
    user_id = api_key_details["user_id"]
    repository.remove_watchlist_pair(mode.value, pair, user_id=user_id)
    return {"status": "removed"}


@router.get("/history/export")
async def export_history(
    repository: SignalRepository = Depends(get_repository),
    api_key_details: dict = Depends(verify_api_key_access),
) -> FileResponse:
    user_id = api_key_details["user_id"]
    output = Path(BASE_DIR) / "logs" / f"signal_history_{user_id}.csv"
    repository.export_history_csv(output, user_id=user_id)
    return FileResponse(output, media_type="text/csv", filename="signal_history.csv")


# ── Admin authentication ─────────────────────────────────────────────

@router.post("/admin/login", response_model=AdminLoginResponse)
async def admin_login(
    body: AdminLoginRequest,
    repository: SignalRepository = Depends(get_repository),
) -> AdminLoginResponse:
    stored_hash = repository.get_admin_password_hash()

    if stored_hash is None:
        raise HTTPException(
            status_code=500,
            detail="Admin config not initialized."
        )

    if not verify_password(body.password, stored_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin password."
        )

    payload = {
        "type": "admin",
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }

    token = jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    return AdminLoginResponse(
        token=token,
        message="Admin login successful.",
    )
    recovery_key: str
    new_password: str


@router.post("/admin/reset-password")
async def admin_reset_password(
    body: AdminResetPasswordRequest,
    repository: SignalRepository = Depends(get_repository),
) -> dict[str, str]:
    """Reset the admin password using a secret recovery key."""
    stored_rec_hash = repository.get_admin_recovery_key_hash()
    if stored_rec_hash is None:
        raise HTTPException(status_code=500, detail="Admin recovery key is not seeded.")
    
    if not verify_password(body.recovery_key.strip(), stored_rec_hash):
        repository.insert_security_alert(
            username="Admin Security",
            email="admin@system.local",
            license_key=None,
            device_id=None,
            alert_type="UNAUTHORIZED_ADMIN_RESET",
            details="Attempted admin password reset with an incorrect Secret Recovery Key."
        )
        raise HTTPException(status_code=401, detail="Invalid recovery key phrase.")
        
    if not body.new_password or len(body.new_password.strip()) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
        
    repository.set_admin_password_hash(hash_password(body.new_password.strip()))
    return {"status": "success", "message": "Admin password has been reset successfully."}


@router.get("/admin/alerts")
async def admin_list_alerts(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[dict]:
    """Retrieve recent security alerts for the admin dashboard."""
    return repository.list_security_alerts()


@router.post("/admin/alerts/clear")
async def admin_clear_alerts(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    """Clear all security alerts from the dashboard."""
    repository.clear_security_alerts()
    return {"status": "success", "message": "Security alerts feed cleared."}


@router.post("/admin/change-password")
async def admin_change_password(
    body: dict,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    """Change admin password. Admin token is sufficient auth (already logged in)."""
    new_password = body.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    repository.set_admin_password_hash(hash_password(new_password))
    return {"status": "Admin password changed successfully."}


# ── Admin license management ─────────────────────────────────────────


# ── User Sign Up & Login ─────────────────────────────────────────────


@router.post("/auth/register")
async def user_register(
    body: UserRegisterRequest,
    repository: SignalRepository = Depends(get_repository),
) -> dict[str, str]:
    username = body.username.strip()
    email = body.email.strip()
    password = body.password
    
    if not username or not email or not password:
        raise HTTPException(status_code=400, detail="All fields are required.")
    
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        
    # Check if username or email already exists
    if repository.get_user_by_username(username) is not None:
        raise HTTPException(status_code=400, detail="Username is already taken.")
        
    password_hash = hash_password(password)
    try:
        repository.insert_user(username, email, password_hash)
        return {"status": "success", "message": "User registered successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}")


@router.post("/auth/login", response_model=UserLoginResponse)
async def user_login(
    body: UserLoginRequest,
    repository: SignalRepository = Depends(get_repository),
) -> UserLoginResponse:
    username = body.username.strip()
    password = body.password
    
    user = repository.get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is suspended.")
        
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
        
    # Generate user session token
    token = secrets.token_urlsafe(32)
    _user_sessions[token] = (user["id"], datetime.now(timezone.utc))
    
    return UserLoginResponse(
        token=token,
        user_id=user["id"],
        username=user["username"],
        email=user["email"],
    )


# ── User API Key Management (User Authenticated) ───────────────────────


@router.post("/user/keys", response_model=CreateApiKeyResponse)
async def create_user_api_key(
    body: CreateApiKeyRequest,
    user_id: int = Depends(verify_user_token),
    repository: SignalRepository = Depends(get_repository),
) -> CreateApiKeyResponse:
    # Generate unique key prefixed with sb_live_
    key = f"sb_live_{secrets.token_hex(16)}"
    
    expires_at = None
    if body.days is not None:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=max(1, body.days))).isoformat()
        
    repository.insert_api_key(user_id=user_id, key=key, name=body.name, expires_at=expires_at)
    return CreateApiKeyResponse(
        key=key,
        name=body.name,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=expires_at,
    )


@router.get("/user/keys")
async def list_user_api_keys(
    user_id: int = Depends(verify_user_token),
    repository: SignalRepository = Depends(get_repository),
) -> list[dict]:
    return repository.list_user_api_keys(user_id)


@router.delete("/user/keys/{key}")
async def revoke_user_api_key(
    key: str,
    user_id: int = Depends(verify_user_token),
    repository: SignalRepository = Depends(get_repository),
) -> dict[str, str]:
    key_details = repository.get_api_key_details(key)
    if key_details is None or key_details["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="API Key not found.")
        
    repository.delete_api_key(key)
    return {"status": "success", "message": "API Key revoked successfully."}


@router.get("/user/profile")
async def get_user_profile(
    user_id: int = Depends(verify_user_token),
    repository: SignalRepository = Depends(get_repository),
) -> dict:
    user = repository.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User account not found.")
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        "role": user["role"],
        "subscription_tier": user["subscription_tier"],
        "subscription_expires_at": user["subscription_expires_at"],
    }


# ── Admin User and Key Management ─────────────────────────────────────


@router.get("/admin/users")
async def admin_list_users(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[dict]:
    return repository.list_users()


@router.patch("/admin/users/{user_id}/status")
async def admin_update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    if not repository.update_user_status(user_id, int(body.is_active)):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "success", "message": "User status updated."}


@router.get("/admin/keys")
async def admin_list_keys(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[dict]:
    return repository.list_all_api_keys()


@router.patch("/admin/keys/{key}/status")
async def admin_update_key_status(
    key: str,
    body: ApiKeyStatusUpdate,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    if not repository.update_api_key_status(key, int(body.is_active)):
        raise HTTPException(status_code=404, detail="API Key not found.")
    return {"status": "success", "message": "API Key status updated."}


class UserSubscriptionUpdate(BaseModel):
    subscription_tier: str
    subscription_expires_at: str | None = None


@router.patch("/admin/users/{user_id}/subscription")
async def admin_update_user_subscription(
    user_id: int,
    body: UserSubscriptionUpdate,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    if not repository.admin_update_user_subscription(user_id, body.subscription_tier, body.subscription_expires_at):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"status": "success", "message": "User subscription details updated."}


# ── Admin License Key Management ──────────────────────────────────────


class CreateLicenseRequest(BaseModel):
    owner: str
    days: int = 365


class LicenseStatusUpdate(BaseModel):
    is_active: bool


@router.post("/admin/licenses")
async def admin_create_license(
    body: CreateLicenseRequest,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict:
    """Admin generates a new license key for a user."""
    key = f"SS-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
    expires_at = (datetime.now(timezone.utc) + timedelta(days=max(1, body.days))).isoformat()
    license_id = repository.insert_license(key=key, owner=body.owner, expires_at=expires_at)
    return {
        "id": license_id,
        "key": key,
        "owner": body.owner,
        "expires_at": expires_at,
        "is_active": True,
    }


@router.get("/admin/licenses")
async def admin_list_licenses(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[dict]:
    """Admin lists all license keys."""
    return repository.list_licenses()


@router.patch("/admin/licenses/{key}/status")
async def admin_update_license_status(
    key: str,
    body: LicenseStatusUpdate,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    """Admin enables/disables a license key."""
    if not repository.update_license_status(key, int(body.is_active)):
        raise HTTPException(status_code=404, detail="License key not found.")
    return {"status": "success", "message": "License status updated."}


@router.delete("/admin/licenses/{key}")
async def admin_delete_license(
    key: str,
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict[str, str]:
    """Admin deletes a license key."""
    if not repository.delete_license(key):
        raise HTTPException(status_code=404, detail="License key not found.")
    return {"status": "success", "message": "License deleted."}


# ── Admin user signal history ─────────────────────────────────────────


@router.get("/admin/users/{user_id}/history")
async def admin_user_history(
    user_id: int,
    limit: int = Query(50, ge=1, le=500),
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> list[dict]:
    """Admin views signal history for a specific user."""
    records = repository.list_history(user_id=user_id, limit=limit)
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "mode": r.mode.value,
            "pair": r.pair,
            "signal": r.signal.value,
            "confidence": r.confidence,
            "duration": r.duration.value,
            "market_trend": r.market_trend,
            "outcome": r.outcome,
        }
        for r in records
    ]


# ── License key login endpoint ────────────────────────────────────────


class LicenseLoginRequest(BaseModel):
    license_key: str
    username: str


class LicenseLoginResponse(BaseModel):
    token: str
    user_id: int
    username: str
    license_key: str
    expires_at: str


@router.post("/auth/license-login", response_model=LicenseLoginResponse)
async def license_login(
    body: LicenseLoginRequest,
    repository: SignalRepository = Depends(get_repository),
) -> LicenseLoginResponse:
    """User logs in using their license key + username."""
    from backend.database.repository import hash_password as _hash_pw
    lic = repository.get_license_by_key(body.license_key.strip())
    if lic is None:
        raise HTTPException(status_code=401, detail="Invalid license key.")

    if not lic.get("is_active"):
        raise HTTPException(status_code=403, detail="License key is disabled by admin.")

    if lic.get("expires_at"):
        exp = datetime.fromisoformat(lic["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="License key has expired.")

    if lic["owner"].lower() != body.username.strip().lower():
        raise HTTPException(status_code=401, detail="License key does not match the given username.")

    user = repository.get_user_by_username(body.username.strip())
    if user is None:
        pw_hash = _hash_pw(secrets.token_hex(16))
        uid = repository.insert_user(
            username=body.username.strip(),
            email=f"{body.username.strip().lower().replace(' ', '_')}@license.local",
            password_hash=pw_hash,
        )
        user = repository.get_user_by_id(uid)

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is suspended.")

    repository.update_license_activity(body.license_key.strip())

    token = secrets.token_urlsafe(32)
    _user_sessions[token] = (user["id"], datetime.now(timezone.utc))

    _mark_user_online(user["id"])
    return LicenseLoginResponse(
        token=token,
        user_id=user["id"],
        username=user["username"],
        license_key=body.license_key.strip(),
        expires_at=lic["expires_at"],
    )


# ── Device-bound license verification ─────────────────────────────────


class LicenseVerifyRequest(BaseModel):
    license_key: str
    device_id: str
    email: str | None = None


class LicenseVerifyResponse(BaseModel):
    status: str  # 'valid' | 'invalid' | 'expired' | 'device_mismatch'
    message: str
    token: str | None = None
    user_id: int | None = None
    username: str | None = None
    expires_at: str | None = None


@router.post("/license/verify", response_model=LicenseVerifyResponse)
async def verify_license(
    body: LicenseVerifyRequest,
    repository: SignalRepository = Depends(get_repository),
) -> LicenseVerifyResponse:
    """
    Verify a license key with device and email binding.
    - If valid and no device registered: bind this device, bind first email, auto-login.
    - If valid and same device/email: auto-login.
    - If valid but different device: reject with 'device_mismatch' and log alert.
    - If valid but different email: reject with mismatch and log alert.
    - If expired: return 'expired'.
    - If invalid: return 'invalid'.
    """
    lic = repository.get_license_by_key(body.license_key.strip())
    if lic is None:
        return LicenseVerifyResponse(
            status="invalid",
            message="Invalid License Key.",
        )

    if not lic.get("is_active"):
        return LicenseVerifyResponse(
            status="invalid",
            message="This license key has been disabled.",
        )

    # Check expiration
    if lic.get("expires_at"):
        exp = datetime.fromisoformat(lic["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return LicenseVerifyResponse(
                status="expired",
                message="License Expired.",
                expires_at=lic["expires_at"],
            )

    # Check device binding
    existing_device = lic.get("device_id")
    if existing_device and existing_device != body.device_id:
        repository.insert_security_alert(
            username=lic["owner"],
            email=body.email or "unregistered@gmail.com",
            license_key=body.license_key.strip(),
            device_id=body.device_id,
            alert_type="DEVICE_MISMATCH",
            details=f"Attempted license activation from unauthorized device '{body.device_id}'. Registered device: '{existing_device}'."
        )
        return LicenseVerifyResponse(
            status="device_mismatch",
            message="This License is already activated on another device.",
        )

    # Find user to check email binding
    owner = lic["owner"]
    user = repository.get_user_by_username(owner)

    if user is not None:
        # Check email binding
        if body.email and user["email"].strip().lower() != body.email.strip().lower():
            repository.insert_security_alert(
                username=owner,
                email=body.email,
                license_key=body.license_key.strip(),
                device_id=body.device_id,
                alert_type="EMAIL_MISMATCH",
                details=f"Attempted license access using unauthorized Gmail '{body.email}'. Registered Gmail: '{user['email']}'."
            )
            return LicenseVerifyResponse(
                status="device_mismatch",
                message="This Gmail is not authorized for this license key. Please contact admin.",
            )

    # Bind device if not yet bound
    if not existing_device:
        repository.activate_license(
            body.license_key.strip(),
            body.device_id,
            app_version="web-1.0",
        )

    # Update activity
    repository.update_license_activity(body.license_key.strip())

    # Create user if it doesn't exist
    if user is None:
        pw_hash = hash_password(secrets.token_hex(16))
        bind_email = body.email.strip() if body.email else f"{owner.lower().replace(' ', '_')}@license.local"
        uid = repository.insert_user(
            username=owner,
            email=bind_email,
            password_hash=pw_hash,
        )
        user = repository.get_user_by_id(uid)

    # Create session
    token = secrets.token_urlsafe(32)
    _user_sessions[token] = (user["id"], datetime.now(timezone.utc))
    _mark_user_online(user["id"])

    return LicenseVerifyResponse(
        status="valid",
        message="License verified successfully. Welcome!",
        token=token,
        user_id=user["id"],
        username=user["username"],
        expires_at=lic["expires_at"],
    )


# ── User heartbeat ────────────────────────────────────────────────────


@router.post("/user/heartbeat")
async def user_heartbeat(
    user_id: int = Depends(verify_user_token),
) -> dict[str, str]:
    """Client pings every 2 minutes to stay 'online'."""
    _mark_user_online(user_id)
    return {"status": "ok"}


# ── Admin Dashboard Stats ─────────────────────────────────────────────


@router.get("/admin/dashboard-stats")
async def admin_dashboard_stats(
    repository: SignalRepository = Depends(get_repository),
    _admin: str = Depends(verify_admin_token),
) -> dict:
    """
    Returns aggregate stats for the admin dashboard:
    - total_users
    - active_users (is_active=1)
    - expired_licenses
    - online_users (heartbeat within 5 min)
    """
    users = repository.list_users()
    licenses = repository.list_licenses()
    now = datetime.now(timezone.utc)

    total_users = len(users)
    active_users = sum(1 for u in users if u.get("is_active"))
    expired_licenses = 0
    for lic in licenses:
        if lic.get("expires_at"):
            exp = datetime.fromisoformat(lic["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                expired_licenses += 1

    online_users = _count_online_users()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "expired_licenses": expired_licenses,
        "online_users": online_users,
        "total_licenses": len(licenses),
        "active_licenses": sum(1 for l in licenses if l.get("is_active")),
    }


# ── WhatsApp Contact ──────────────────────────────────────────────────


WHATSAPP_NUMBER = "923224914560"
WHATSAPP_MESSAGE = "Hello, I want to purchase an API/License Key."


@router.get("/contact/whatsapp")
async def whatsapp_contact() -> dict:
    """Return the pre-filled WhatsApp link."""
    import urllib.parse
    encoded = urllib.parse.quote(WHATSAPP_MESSAGE)
    return {
        "url": f"https://wa.me/{WHATSAPP_NUMBER}?text={encoded}",
        "number": WHATSAPP_NUMBER,
        "message": WHATSAPP_MESSAGE,
    }

