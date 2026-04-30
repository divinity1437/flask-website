import os
import requests
from flask import Blueprint, redirect, url_for, session, request, render_template
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

print(f"Using CLIENT_ID: {CLIENT_ID}")
print(f"Using REDIRECT_URI: {REDIRECT_URI}")

auth_bp = Blueprint('auth', __name__)

CLIENT_ID = os.environ.get("OSU_CLIENT_ID")
CLIENT_SECRET = os.environ.get("OSU_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("OSU_REDIRECT_URI", "https://okayu.click/auth/callback")

@auth_bp.route('/auth/login')
def login():
    if not CLIENT_ID:
        return "OAuth not configured: OSU_CLIENT_ID is missing", 500
    
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'identify public'
    }
    auth_url = "https://osu.ppy.sh/oauth/authorize?" + urlencode(params)
    return redirect(auth_url)

@auth_bp.route('/auth/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return "Authorization failed (no code)", 400

    if not CLIENT_ID or not CLIENT_SECRET:
        return "OAuth not configured properly", 500

    token_url = "https://osu.ppy.sh/oauth/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Token exchange failed: {response.text}", 400

    token_data = response.json()
    access_token = token_data.get('access_token')

    user_response = requests.get(
        'https://osu.ppy.sh/api/v2/me',
        headers={'Authorization': f'Bearer {access_token}'}
    )

    if user_response.status_code == 200:
        user_data = user_response.json()
        session['user'] = {
            'id': user_data['id'],
            'username': user_data['username'],
            'avatar_url': user_data['avatar_url'],
            'country_code': user_data['country']['code'],
            'server': 'bancho'  #标记来自Bancho
        }
    else:
        return f"Failed to get user data: {user_response.text}", 400

    return redirect(url_for('inspector.inspector_index', username=session['user']['username']))

@auth_bp.route('/auth/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('inspector.inspector_index'))