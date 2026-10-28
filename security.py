import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from flask import abort, request, session

_rate_lock = threading.Lock()
_rate_events = defaultdict(deque)


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    expected = session.get("_csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400)


def limit_requests(key, limit, window):
    now = time.monotonic()
    cutoff = now - window
    with _rate_lock:
        events = _rate_events[key]
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        if len(_rate_events) > 10000:
            for old_key in tuple(_rate_events):
                if not _rate_events[old_key] or _rate_events[old_key][-1] <= cutoff:
                    _rate_events.pop(old_key, None)
    return True


def enforce_rate_limit(name, limit, window):
    key = f"{name}:{request.remote_addr or 'unknown'}"
    if not limit_requests(key, limit, window):
        abort(429)
