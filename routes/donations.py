import json
import fcntl
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from config import BASE_URL, INSTANCE_DIR, env
from security import enforce_rate_limit

try:
    import websocket
except ImportError:
    websocket = None

donations_bp = Blueprint("donations", __name__)
API_BASE = "https://www.donationalerts.com/api/v1"
TOKEN_URL = "https://www.donationalerts.com/oauth/token"
AUTHORIZE_URL = "https://www.donationalerts.com/oauth/authorize"
CENTRIFUGO_URL = "wss://centrifugo.donationalerts.com/connection/websocket"
GOAL_POLL_INTERVAL = 15
STORE_PATH = Path(env("DONATIONALERTS_TOKEN_STORE", str(INSTANCE_DIR / "donationalerts-oauth.json")))
STORE_DIR = STORE_PATH.parent
STATE_PATH = STORE_DIR / "donation-goal.json"
_store_lock = threading.RLock()
_listener_lock = threading.Lock()
_listener_started = False
_goal_lock = threading.Lock()
_goal = None
_goal_token_lock = threading.Lock()
_goal_token_cache = {"token": None, "fetched_at": 0.0}
_listener_lock_path = INSTANCE_DIR / "donationalerts-listener.lock"


def _credentials():
    return env("DONATIONALERTS_CLIENT_ID"), env("DONATIONALERTS_CLIENT_SECRET")


def _goal_id():
    return env("DONATIONALERTS_GOAL_ID")


def _owner_id():
    try:
        return int(env("DONATIONALERTS_ADMIN_OSU_ID", ""))
    except ValueError:
        return None


def _redirect_uri():
    return env("DONATIONALERTS_REDIRECT_URI", f"{BASE_URL}/donationalerts/callback")


def _read_store():
    try:
        with STORE_PATH.open(encoding="utf-8") as store_file:
            data = json.load(store_file)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_store(data):
    STORE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = STORE_PATH.with_name(f"{STORE_PATH.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as store_file:
        json.dump(data, store_file)
        store_file.flush()
        os.fsync(store_file.fileno())
    os.replace(temporary_path, STORE_PATH)


def _save_token_response(token_data, existing=None):
    existing = existing or {}
    data = {
        "access_token": token_data.get("access_token", existing.get("access_token")),
        "refresh_token": token_data.get("refresh_token", existing.get("refresh_token")),
        "expires_at": time.time() + int(token_data.get("expires_in", 0)),
    }
    with _store_lock:
        _write_store(data)
    return data


def _access_token():
    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return None
    with _store_lock:
        STORE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = STORE_PATH.with_suffix(STORE_PATH.suffix + ".lock")
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            stored = _read_store()
            if stored.get("access_token") and stored.get("expires_at", 0) > time.time() + 60:
                return stored["access_token"]
            refresh_token = stored.get("refresh_token")
            if not refresh_token:
                return None
            try:
                response = requests.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "scope": "oauth-user-show oauth-goal-subscribe",
                    },
                    timeout=(5, 15),
                )
                response.raise_for_status()
                return _save_token_response(response.json(), stored)["access_token"]
            except (requests.RequestException, ValueError, TypeError, OSError) as error:
                current_app.logger.warning("DonationAlerts token refresh failed: %s", type(error).__name__)
                return None
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_goal(resource):
    if not isinstance(resource, dict):
        return None
    expected_id = _goal_id()
    goal_id = str(resource.get("id", ""))
    if not expected_id or goal_id != expected_id:
        return None
    active_value = resource.get("is_active")
    raised = _to_float(resource.get("raised_amount", 0))
    start_amount = _to_float(resource.get("start_amount", 0))
    target = _to_float(resource.get("goal_amount", 0))
    return {
        "id": goal_id,
        "title": str(resource.get("title") or "Donation goal")[:160],
        "currency": str(resource.get("currency") or "")[:8],
        "raised_amount": raised,
        "start_amount": start_amount,
        "goal_amount": target,
        "progress_amount": raised,
        "is_active": active_value is True or active_value == 1 or active_value == "1",
        "updated_at": time.time(),
    }


def _extract_widget_token(html):
    match = re.search(r'token_widget_streamer\s*=\s*"([^"]+)"', html)
    return match.group(1) if match else None


def _widget_goal_token():
    now = time.time()
    with _goal_token_lock:
        cached = _goal_token_cache["token"]
        if cached and now - _goal_token_cache["fetched_at"] < 3600:
            return cached
        widget_url = env("DONATIONALERTS_GOAL_URL")
        if not widget_url:
            raise RuntimeError("DonationAlerts goal URL is not configured")
        response = requests.get(widget_url, headers={"User-Agent": "osu-tools/1.0"}, timeout=(5, 15))
        response.raise_for_status()
        token = _extract_widget_token(response.text)
        if not token:
            raise RuntimeError("DonationAlerts widget token was not found")
        _goal_token_cache.update(token=token, fetched_at=now)
        return token


def _fetch_current_goal():
    goal_id = _goal_id()
    if not goal_id:
        raise RuntimeError("DonationAlerts goal ID is not configured")
    token = _widget_goal_token()
    response = requests.get(
        f"{API_BASE}/donationgoal/{goal_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={"include_timestamps": 1},
        timeout=(5, 15),
    )
    response.raise_for_status()
    payload = response.json()
    return _normalize_goal(payload.get("data")) if isinstance(payload, dict) else None


def _record_goal(resource):
    global _goal
    if isinstance(resource, dict) and isinstance(resource.get("goal"), dict):
        resource = resource["goal"]
    goal = _normalize_goal(resource)
    if not goal:
        return
    with _goal_lock:
        if _goal and {key: value for key, value in _goal.items() if key != "updated_at"} == {key: value for key, value in goal.items() if key != "updated_at"}:
            return
        _goal = goal
        STORE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_path = STATE_PATH.with_name(f"{STATE_PATH.name}.{os.getpid()}.tmp")
        descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
            json.dump(goal, state_file)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary_path, STATE_PATH)


def _load_goal():
    with _goal_lock:
        if _goal:
            return dict(_goal)
        try:
            with STATE_PATH.open(encoding="utf-8") as state_file:
                state = json.load(state_file)
        except (OSError, ValueError):
            return None
    return _normalize_goal(state)


def _handle_ws_message(message):
    if not isinstance(message, dict):
        return
    push = message.get("push") or {}
    pub = (push.get("pub") or {}) if isinstance(push, dict) else {}
    payload = pub.get("data") if isinstance(pub, dict) else None
    if payload is None:
        result = message.get("result") or {}
        payload = result.get("data") if isinstance(result, dict) else None
    if isinstance(payload, dict):
        _record_goal(payload)


def _poll_for_goals():
    while True:
        try:
            _record_goal(_fetch_current_goal())
        except Exception as error:
            current_app.logger.warning("DonationAlerts goal fetch failed: %s", type(error).__name__)
        time.sleep(GOAL_POLL_INTERVAL)


def _listen_for_goals():
    if websocket is None:
        current_app.logger.error("DonationAlerts listener requires websocket-client")
        return
    while True:
        ws = None
        try:
            token = _access_token()
            if not token:
                time.sleep(30)
                continue
            user_response = requests.get(f"{API_BASE}/user/oauth", headers={"Authorization": f"Bearer {token}"}, timeout=(5, 15))
            user_response.raise_for_status()
            user_data = user_response.json()["data"]
            user_id = user_data["id"]
            socket_token = user_data["socket_connection_token"]
            channel = f"$goals:goal_{user_id}"
            ws = websocket.create_connection(CENTRIFUGO_URL, timeout=25)
            ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
            hello = json.loads(ws.recv())
            client_id = hello["result"]["client"]
            subscription = requests.post(
                f"{API_BASE}/centrifuge/subscribe",
                headers={"Authorization": f"Bearer {token}"},
                json={"channels": [channel], "client": client_id},
                timeout=(5, 15),
            )
            subscription.raise_for_status()
            channel_token = subscription.json()["channels"][0]["token"]
            ws.send(json.dumps({"params": {"channel": channel, "token": channel_token}, "method": 1, "id": 2}))
            ws.recv()
            ws.settimeout(30)
            while True:
                try:
                    _handle_ws_message(json.loads(ws.recv()))
                except websocket.WebSocketTimeoutException:
                    continue
        except Exception as error:
            current_app.logger.warning("DonationAlerts stream disconnected: %s", type(error).__name__)
            time.sleep(5)
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass


def start_goal_listener(app):
    global _listener_started
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return
    with _listener_lock:
        if _listener_started:
            return
        _listener_started = True
    INSTANCE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_file = _listener_lock_path.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return

    def run_listener(lock_handle=lock_file):
        try:
            with app.app_context():
                _listen_for_goals()
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()

    def run_poller():
        with app.app_context():
            _poll_for_goals()

    threading.Thread(target=run_listener, name="donationalerts-goals", daemon=True).start()
    threading.Thread(target=run_poller, name="donationalerts-goal-poller", daemon=True).start()


@donations_bp.route("/donationalerts/connect")
def connect():
    enforce_rate_limit("donations-connect", 10, 3600)
    owner_id = _owner_id()
    user = session.get("user") or {}
    if not user:
        session["after_osu_login"] = "donations.connect"
        return redirect(url_for("auth.login"))
    if owner_id is None:
        return "DonationAlerts owner is not configured", 503
    try:
        if int(user.get("id", 0)) != owner_id:
            return "Forbidden.", 403
    except (TypeError, ValueError):
        return "Forbidden.", 403
    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return "DonationAlerts OAuth is not configured.", 503
    if not _goal_id():
        return "DonationAlerts goal is not configured.", 503
    state = secrets.token_urlsafe(32)
    session["donationalerts_oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "oauth-user-show oauth-goal-subscribe",
        "state": state,
    }
    return redirect(f"{AUTHORIZE_URL}?{urlencode(params)}")


@donations_bp.route("/donationalerts/callback")
def callback():
    owner_id = _owner_id()
    user = session.get("user") or {}
    try:
        if owner_id is None or int(user.get("id", 0)) != owner_id:
            return "Forbidden.", 403
    except (TypeError, ValueError):
        return "Forbidden.", 403
    expected_state = session.pop("donationalerts_oauth_state", None)
    if not expected_state or not secrets.compare_digest(expected_state, request.args.get("state", "")):
        return "DonationAlerts authorization state mismatch.", 400
    if request.args.get("error"):
        return "DonationAlerts authorization was denied.", 400
    client_id, client_secret = _credentials()
    code = request.args.get("code")
    if not client_id or not client_secret or not code:
        return "DonationAlerts OAuth is not configured.", 503
    try:
        response = requests.post(
            TOKEN_URL,
            data={"grant_type": "authorization_code", "client_id": client_id, "client_secret": client_secret, "redirect_uri": _redirect_uri(), "code": code, "scope": "oauth-user-show oauth-goal-subscribe"},
            timeout=(5, 15),
        )
        response.raise_for_status()
        token_data = response.json()
        if not token_data.get("access_token") or not token_data.get("refresh_token"):
            return "DonationAlerts authorization failed.", 502
        _save_token_response(token_data)
    except (requests.RequestException, ValueError, TypeError, OSError) as error:
        current_app.logger.warning("DonationAlerts OAuth failed: %s", type(error).__name__)
        return "DonationAlerts authorization failed.", 502
    start_goal_listener(current_app._get_current_object())
    return redirect(url_for("home.donation_goals"))


@donations_bp.route("/donationgoals/api/current")
def current_goal():
    goal = _load_goal()
    if not goal:
        return jsonify({"available": False}), 503
    return jsonify({"available": True, "goal": goal})
