import json
import os
import re
import secrets
import threading
import time
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

try:
    import websocket
except ImportError:
    websocket = None


donations_bp = Blueprint('donations', __name__)
API_BASE = 'https://www.donationalerts.com/api/v1'
TOKEN_URL = 'https://www.donationalerts.com/oauth/token'
AUTHORIZE_URL = 'https://www.donationalerts.com/oauth/authorize'
CENTRIFUGO_URL = 'wss://centrifugo.donationalerts.com/connection/websocket'
DEFAULT_GOAL_ID = '6882493'
GOAL_POLL_INTERVAL = 15
STORE_PATH = os.environ.get(
    'DONATIONALERTS_TOKEN_STORE',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'donationalerts-oauth.json')
)
STORE_DIR = os.path.dirname(STORE_PATH) or '.'

_store_lock = threading.RLock()
_listener_lock = threading.Lock()
_listener_started = False
_goal_lock = threading.Lock()
_goal = None


def _credentials():
    return os.environ.get('DONATIONALERTS_CLIENT_ID'), os.environ.get('DONATIONALERTS_CLIENT_SECRET')


def _read_store():
    try:
        with open(STORE_PATH, encoding='utf-8') as store_file:
            return json.load(store_file)
    except (OSError, ValueError):
        return {}


def _write_store(data):
    os.makedirs(STORE_DIR, mode=0o700, exist_ok=True)
    temporary_path = f'{STORE_PATH}.{os.getpid()}.tmp'
    with open(temporary_path, 'w', encoding='utf-8') as store_file:
        os.chmod(temporary_path, 0o600)
        json.dump(data, store_file)
    os.replace(temporary_path, STORE_PATH)


def _save_token_response(token_data, existing=None):
    existing = existing or {}
    data = {
        'access_token': token_data.get('access_token', existing.get('access_token')),
        'refresh_token': token_data.get('refresh_token', existing.get('refresh_token')),
        'expires_at': time.time() + int(token_data.get('expires_in', 0)),
    }
    with _store_lock:
        _write_store(data)
    return data


def _access_token():
    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return None

    with _store_lock:
        stored = _read_store()
        if stored.get('access_token') and stored.get('expires_at', 0) > time.time() + 60:
            return stored['access_token']
        refresh_token = stored.get('refresh_token')

    if not refresh_token:
        return None

    response = requests.post(TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'scope': 'oauth-user-show oauth-goal-subscribe',
    }, timeout=15)
    response.raise_for_status()
    with _store_lock:
        return _save_token_response(response.json(), stored)['access_token']


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_goal(resource):
    if not isinstance(resource, dict):
        return None

    goal_id = str(resource.get('id', ''))
    expected_id = os.environ.get('DONATIONALERTS_GOAL_ID', DEFAULT_GOAL_ID)
    if goal_id != expected_id:
        return None

    active_value = resource.get('is_active')
    raised = _to_float(resource.get('raised_amount', 0))
    start_amount = _to_float(resource.get('start_amount', 0))
    target = _to_float(resource.get('goal_amount', 0))

    return {
        'id': goal_id,
        'title': str(resource.get('title') or 'Donation goal')[:160],
        'currency': str(resource.get('currency') or '')[:8],
        'raised_amount': raised,
        'start_amount': start_amount,
        'goal_amount': target,
        'progress_amount': raised,
        'is_active': active_value is True or active_value == 1 or active_value == '1',
        'updated_at': time.time(),
    }


_goal_token_lock = threading.Lock()
_goal_token_cache = {'token': None, 'fetched_at': 0.0}


def _extract_widget_token(html):
    match = re.search(r'token_widget_streamer\s*=\s*"([^"]+)"', html)
    return match.group(1) if match else None


def _widget_goal_token():
    now = time.time()
    with _goal_token_lock:
        cached = _goal_token_cache['token']
        if cached and now - _goal_token_cache['fetched_at'] < 3600:
            return cached

    widget_url = os.environ.get('DONATIONALERTS_GOAL_URL')
    if not widget_url:
        raise RuntimeError('DONATIONALERTS_GOAL_URL is not configured')
    response = requests.get(
        widget_url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; osu-tools/1.0)'},
        timeout=15,
    )
    response.raise_for_status()
    token = _extract_widget_token(response.text)
    if not token:
        raise RuntimeError('DonationAlerts widget token not found in page')

    with _goal_token_lock:
        _goal_token_cache['token'] = token
        _goal_token_cache['fetched_at'] = now
    return token


def _fetch_current_goal():
    goal_id = os.environ.get('DONATIONALERTS_GOAL_ID', DEFAULT_GOAL_ID)
    token = _widget_goal_token()
    response = requests.get(
        f'{API_BASE}/donationgoal/{goal_id}',
        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'},
        params={'include_timestamps': 1},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    resource = payload.get('data') if isinstance(payload, dict) else None
    return _normalize_goal(resource)


def _record_goal(resource):
    global _goal
    if not isinstance(resource, dict):
        return
    if isinstance(resource.get('goal'), dict):
        resource = resource['goal']
    goal = _normalize_goal(resource)
    if not goal:
        return
    with _goal_lock:
        _goal = goal
        os.makedirs(STORE_DIR, mode=0o700, exist_ok=True)
        state_path = os.path.join(STORE_DIR, 'donation-goal.json')
        temporary_path = f'{state_path}.{os.getpid()}.tmp'
        with open(temporary_path, 'w', encoding='utf-8') as state_file:
            os.chmod(temporary_path, 0o600)
            json.dump(goal, state_file)
        os.replace(temporary_path, state_path)


def _load_goal():
    with _goal_lock:
        if _goal:
            return dict(_goal)
        state_path = os.path.join(STORE_DIR, 'donation-goal.json')
        try:
            with open(state_path, encoding='utf-8') as state_file:
                state = json.load(state_file)
        except (OSError, ValueError):
            return None
        normalized = _normalize_goal(state)
        return normalized


def _handle_ws_message(message):
    payload = message.get('push', {}).get('pub', {}).get('data')
    if payload is None:
        result = message.get('result', {})
        payload = result.get('data') if isinstance(result, dict) else None
    if isinstance(payload, dict):
        _record_goal(payload)


def _poll_for_goals():
    while True:
        try:
            _record_goal(_fetch_current_goal())
        except Exception as error:
            current_app.logger.warning('DonationAlerts goal fetch failed: %s', error)
        time.sleep(GOAL_POLL_INTERVAL)


def _listen_for_goals():
    if websocket is None:
        current_app.logger.error('DonationAlerts listener requires websocket-client')
        return

    while True:
        try:
            token = _access_token()
            if not token:
                time.sleep(30)
                continue

            user_response = requests.get(
                f'{API_BASE}/user/oauth',
                headers={'Authorization': f'Bearer {token}'},
                timeout=15,
            )
            user_response.raise_for_status()
            user_data = user_response.json()
            user_id = user_data['data']['id']
            socket_token = user_data['data']['socket_connection_token']
            channel = f'$goals:goal_{user_id}'

            ws = websocket.create_connection(CENTRIFUGO_URL, timeout=25)
            ws.send(json.dumps({'params': {'token': socket_token}, 'id': 1}))
            hello = json.loads(ws.recv())
            client_id = hello['result']['client']

            subscription = requests.post(
                f'{API_BASE}/centrifuge/subscribe',
                headers={'Authorization': f'Bearer {token}'},
                json={'channels': [channel], 'client': client_id},
                timeout=15,
            )
            subscription.raise_for_status()
            channel_token = subscription.json()['channels'][0]['token']
            ws.send(json.dumps({
                'params': {'channel': channel, 'token': channel_token},
                'method': 1,
                'id': 2,
            }))
            ws.recv()
            ws.settimeout(30)

            while True:
                try:
                    message = json.loads(ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                _handle_ws_message(message)
        except Exception as error:
            current_app.logger.warning('DonationAlerts goal stream disconnected: %s', error)
            time.sleep(5)


def start_goal_listener(app):
    global _listener_started
    with _listener_lock:
        if _listener_started:
            return
        _listener_started = True

    def run_listener():
        with app.app_context():
            _listen_for_goals()

    def run_poller():
        with app.app_context():
            _poll_for_goals()

    threading.Thread(target=run_listener, name='donationalerts-goals', daemon=True).start()
    threading.Thread(target=run_poller, name='donationalerts-goal-poller', daemon=True).start()


@donations_bp.route('/donationalerts/connect')
def connect():
    owner_id = int(os.environ.get('DONATIONALERTS_ADMIN_OSU_ID', '10081838'))
    user = session.get('user') or {}
    if not user:
        session['after_osu_login'] = 'donations.connect'
        return redirect(url_for('auth.login'))
    if int(user.get('id', 0)) != owner_id:
        return 'Forbidden.', 403

    client_id, client_secret = _credentials()
    if not client_id or not client_secret:
        return 'DonationAlerts OAuth is not configured.', 503

    redirect_uri = os.environ.get(
        'DONATIONALERTS_REDIRECT_URI',
        url_for('donations.callback', _external=True),
    )
    state = secrets.token_urlsafe(32)
    session['donationalerts_oauth_state'] = state
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'oauth-user-show oauth-goal-subscribe',
        'state': state,
    }
    return redirect(f'{AUTHORIZE_URL}?{urlencode(params)}')


@donations_bp.route('/donationalerts/callback')
def callback():
    owner_id = int(os.environ.get('DONATIONALERTS_ADMIN_OSU_ID', '10081838'))
    user = session.get('user') or {}
    if int(user.get('id', 0)) != owner_id:
        return 'Forbidden.', 403

    expected_state = session.pop('donationalerts_oauth_state', None)
    if not expected_state or not secrets.compare_digest(expected_state, request.args.get('state', '')):
        return 'DonationAlerts authorization state mismatch.', 400
    if request.args.get('error'):
        return 'DonationAlerts authorization was denied.', 400

    client_id, client_secret = _credentials()
    redirect_uri = os.environ.get(
        'DONATIONALERTS_REDIRECT_URI',
        url_for('donations.callback', _external=True),
    )
    response = requests.post(TOKEN_URL, data={
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'code': request.args.get('code', ''),
        'scope': 'oauth-user-show oauth-goal-subscribe',
    }, timeout=15)
    response.raise_for_status()
    _save_token_response(response.json())
    start_goal_listener(current_app._get_current_object())
    return redirect(url_for('home.donation_goals'))


@donations_bp.route('/donationgoals/api/current')
def current_goal():
    goal = _load_goal()
    if not goal:
        return jsonify({'available': False}), 503
    return jsonify({'available': True, 'goal': goal})
