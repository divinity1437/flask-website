import logging
import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, redirect, session, request, url_for

from config import BASE_URL, env

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


def credentials():
    return env("OSU_CLIENT_ID"), env("OSU_CLIENT_SECRET")


def redirect_uri():
    return env("OSU_REDIRECT_URI", f"{BASE_URL}/auth/callback")


@auth_bp.route("/auth/login")
def login():
    client_id, client_secret = credentials()
    if not client_id:
        return "OAuth not configured", 503
    state = secrets.token_urlsafe(32)
    session["osu_oauth_state"] = state
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "identify public",
        "state": state,
    }
    return redirect("https://osu.ppy.sh/oauth/authorize?" + urlencode(params))


@auth_bp.route("/auth/callback")
def callback():
    expected_state = session.pop("osu_oauth_state", None)
    received_state = request.args.get("state", "")
    if not expected_state or not secrets.compare_digest(expected_state, received_state):
        return "Authorization state mismatch", 400
    if request.args.get("error"):
        return "Authorization was denied", 400
    code = request.args.get("code")
    client_id, client_secret = credentials()
    if not code or not client_id or not client_secret:
        return "Authorization failed", 400

    try:
        response = requests.post(
            "https://osu.ppy.sh/oauth/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(),
            },
            timeout=(5, 15),
        )
        response.raise_for_status()
        access_token = response.json().get("access_token")
        if not access_token:
            return "Authorization failed", 400
        user_response = requests.get(
            "https://osu.ppy.sh/api/v2/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=(5, 15),
        )
        user_response.raise_for_status()
        user_data = user_response.json()
    except (requests.RequestException, ValueError, KeyError) as error:
        logger.warning("osu! OAuth callback failed: %s", type(error).__name__)
        return "Authorization failed", 502

    country = user_data.get("country") or {}
    after_login = session.get("after_osu_login")
    session.clear()
    session["user"] = {
        "id": user_data.get("id"),
        "username": user_data.get("username", ""),
        "avatar_url": user_data.get("avatar_url", ""),
        "country_code": country.get("code", ""),
        "server": "bancho",
    }
    if after_login == "donations.connect":
        return redirect(url_for("donations.connect"))
    return redirect(url_for("inspector.inspector_index", username=session["user"]["username"]))


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return redirect(url_for("inspector.inspector_index"))
