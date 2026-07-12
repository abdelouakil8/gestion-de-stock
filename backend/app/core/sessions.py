"""In-memory session store for the local multi-user auth.

After a PIN login the API issues a short-lived opaque session token (a UUID
hex) mapped to the authenticated user. Because the backend runs in-process and
restarts with the desktop app, an in-memory store with a TTL is sufficient — no
persistence is needed (a restart simply forces a re-login). Access is guarded
by a lock since FastAPI serves sync endpoints from a thread pool.
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_TTL = timedelta(hours=12)
_lock = threading.Lock()
_sessions: dict[str, "Session"] = {}


@dataclass(frozen=True)
class Session:
    token: str
    user_id: uuid.UUID
    store_id: uuid.UUID
    name: str
    role: str
    expires_at: datetime


def create(user) -> Session:
    """Issue a session for an authenticated User and store it."""
    session = Session(
        token=uuid.uuid4().hex,
        user_id=user.id,
        store_id=user.store_id,
        name=user.name,
        role=str(user.role),
        expires_at=datetime.now(UTC) + _TTL,
    )
    with _lock:
        _sessions[session.token] = session
    return session


def get(token: str | None) -> "Session | None":
    """Return the live session for a token, or None if missing/expired."""
    if not token:
        return None
    now = datetime.now(UTC)
    with _lock:
        session = _sessions.get(token)
        if session is None:
            return None
        if session.expires_at <= now:
            _sessions.pop(token, None)
            return None
        return session


def revoke(token: str | None) -> None:
    if token:
        with _lock:
            _sessions.pop(token, None)


def clear() -> None:
    """Drop every session (used by tests and factory reset)."""
    with _lock:
        _sessions.clear()
