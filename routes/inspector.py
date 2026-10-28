import logging
import os
import threading
import time
from urllib.parse import quote

import requests
from flask import Blueprint, Response, jsonify, render_template, request, session

from security import enforce_rate_limit

logger = logging.getLogger(__name__)
inspector_bp = Blueprint("inspector", __name__, template_folder="../templates")
MODES = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}
SUBMODES_OKAYU = {
    0: {"name": "Vanilla", "icon": "🎯", "description": "Standard"},
    4: {"name": "Relax", "icon": "😌", "description": "Manual aim, auto tap"},
    8: {"name": "Autopilot", "icon": "🤖", "description": "Auto aim, manual tap"},
}
_bancho_token = None
_token_expiry = 0
_token_lock = threading.Lock()
_availability_cache = {}
_availability_lock = threading.Lock()


def get_bancho_token():
    global _bancho_token, _token_expiry
    if _bancho_token and time.time() < _token_expiry:
        return _bancho_token
    client_id = os.environ.get("OSU_CLIENT_ID")
    client_secret = os.environ.get("OSU_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    with _token_lock:
        if _bancho_token and time.time() < _token_expiry:
            return _bancho_token
        try:
            response = requests.post(
                "https://osu.ppy.sh/oauth/token",
                data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials", "scope": "public"},
                timeout=(5, 15),
            )
            response.raise_for_status()
            token_data = response.json()
            _bancho_token = token_data.get("access_token")
            _token_expiry = time.time() + max(0, int(token_data.get("expires_in", 3600)) - 60)
            return _bancho_token
        except (requests.RequestException, ValueError, TypeError) as error:
            logger.warning("Bancho token request failed: %s", type(error).__name__)
            return None


def get_osu_user_bancho(username, mode=0):
    token = get_bancho_token()
    if not token:
        return None
    mode_str = MODES.get(mode, "osu")
    url = f"https://osu.ppy.sh/api/v2/users/@{quote(username, safe='')}/{mode_str}"
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}, timeout=(5, 10))
        if response.status_code != 200:
            return None
        data = response.json()
        return transform_bancho_data(data, mode) if isinstance(data, dict) else None
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Bancho user lookup failed: %s", type(error).__name__)
        return None


def transform_bancho_data(bancho_user, mode):
    stats = bancho_user.get("statistics") or {}
    if not isinstance(stats, dict):
        stats = {}
    level = stats.get("level") or {}
    grades = stats.get("grade_counts") or {}
    mode_stats = {
        "pp": round(stats.get("pp") or 0),
        "rank": stats.get("global_rank") or 0,
        "country_rank": stats.get("country_rank") or 0,
        "acc": round(stats.get("hit_accuracy") or 0, 2),
        "plays": stats.get("play_count") or 0,
        "total_score": stats.get("total_score") or 0,
        "total_hits": stats.get("total_hits") or 0,
        "level": int(level.get("current", 1)) if isinstance(level, dict) else 1,
        "counts_ss": grades.get("ss", 0) if isinstance(grades, dict) else 0,
        "counts_s": grades.get("s", 0) if isinstance(grades, dict) else 0,
        "counts_a": grades.get("a", 0) if isinstance(grades, dict) else 0,
    }
    rank = mode_stats["rank"]
    mode_stats["pp_progress"] = min(100, (mode_stats["pp"] % 1000) / 10) if rank and rank < 10000 else 50
    country = bancho_user.get("country") or {}
    cover = bancho_user.get("cover") or {}
    return {
        "info": {
            "id": bancho_user.get("id"),
            "name": bancho_user.get("username", ""),
            "country": country.get("code", "") if isinstance(country, dict) else "",
            "country_code": country.get("code", "") if isinstance(country, dict) else "",
            "cover_url": cover.get("url") if isinstance(cover, dict) else None,
            "avatar_url": bancho_user.get("avatar_url"),
        },
        "stats": {str(mode): mode_stats},
    }


def get_osu_user_okayu(username):
    try:
        response = requests.get("https://api.osuokayu.pw/v1/get_player_info", params={"name": username, "scope": "all"}, timeout=(3, 8))
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict) or data.get("status") != "success" or not isinstance(data.get("player"), dict):
            return None
        player = data["player"]
        stats = player.get("stats")
        if isinstance(stats, dict):
            for item in stats.values():
                if isinstance(item, dict) and item.get("level") is None:
                    total = item.get("total_score") or 0
                    item["level"] = int(total ** 0.4 * 0.2) if total > 0 else 1
        info = player.get("info") or {}
        if isinstance(info, dict) and info.get("id"):
            info["cover_url"] = f"https://osuokayu.pw/banners/{quote(str(info['id']), safe='')}"
            info["avatar_url"] = f"https://a.osuokayu.pw/{quote(str(info['id']), safe='')}"
        return player
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Okayu user lookup failed: %s", type(error).__name__)
        return None


def get_player_status_okayu(username):
    try:
        response = requests.get("https://api.osuokayu.pw/v1/get_player_status", params={"name": username}, timeout=(3, 8))
        data = response.json()
        status = data.get("player_status") if isinstance(data, dict) else None
        return (bool(status.get("online")), status.get("last_seen")) if isinstance(status, dict) and data.get("status") == "success" else (False, None)
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Okayu status lookup failed: %s", type(error).__name__)
        return False, None


def get_top_scores_okayu(username, mode=0, limit=5):
    try:
        response = requests.get("https://api.osuokayu.pw/v1/get_player_scores", params={"name": username, "scope": "best", "limit": limit, "mode": mode}, timeout=(3, 8))
        data = response.json()
        if not isinstance(data, dict) or data.get("status") != "success":
            return []
        scores = data.get("scores", [])
        if not isinstance(scores, list):
            return []
        for score in scores:
            if isinstance(score, dict) and "mods" in score:
                score["mods_readable"] = mods_to_readable(score.get("mods", 0))
        return scores
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Okayu scores lookup failed: %s", type(error).__name__)
        return []


def get_top_scores_bancho(username, mode=0, limit=5):
    token = get_bancho_token()
    if not token:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    try:
        user_response = requests.get(f"https://osu.ppy.sh/api/v2/users/@{quote(username, safe='')}", headers=headers, timeout=(5, 10))
        if user_response.status_code != 200:
            return []
        user_id = user_response.json().get("id")
        if not user_id:
            return []
        response = requests.get(
            f"https://osu.ppy.sh/api/v2/users/{int(user_id)}/scores/best",
            headers=headers,
            params={"limit": min(max(int(limit), 1), 5), "mode": MODES.get(mode, "osu")},
            timeout=(5, 10),
        )
        if response.status_code != 200:
            return []
        scores = response.json()
        return [format_bancho_score(score) for score in scores if isinstance(score, dict)] if isinstance(scores, list) else []
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.warning("Bancho score lookup failed: %s", type(error).__name__)
        return []


def format_bancho_score(score):
    statistics = score.get("statistics") or {}
    beatmap = score.get("beatmap") or {}
    beatmapset = score.get("beatmapset") or {}
    weight = score.get("weight") or {}
    mods = score.get("mods") or []
    return {
        "pp": score.get("pp", 0), "score": score.get("score", 0), "acc": (score.get("accuracy") or 0) * 100,
        "mods_readable": "+".join(mods) if mods else "NM", "max_combo": score.get("max_combo", 0),
        "n300": statistics.get("count_300", 0), "n100": statistics.get("count_100", 0),
        "n50": statistics.get("count_50", 0), "nmiss": statistics.get("count_miss", 0),
        "ngeki": statistics.get("count_geki", 0), "nkatu": statistics.get("count_katu", 0),
        "rank": score.get("rank", "F"), "created_at": score.get("created_at", ""), "id": score.get("id", 0),
        "has_replay": bool(score.get("replay", False)), "beatmap_id": beatmap.get("id", 0),
        "beatmapset_id": beatmap.get("beatmapset_id", 0),
        "beatmap": {"id": beatmap.get("id", 0), "title": beatmapset.get("title", "Unknown"), "artist": beatmapset.get("artist", "Unknown"), "version": beatmap.get("version", "Unknown"), "beatmapset_id": beatmap.get("beatmapset_id", 0)},
        "beatmapset": {"id": beatmap.get("beatmapset_id", 0), "title": beatmapset.get("title", "Unknown"), "artist": beatmapset.get("artist", "Unknown")},
        "weight_pp": weight.get("pp", 0), "weight_percentage": weight.get("percentage", 0),
    }


def mods_to_readable(mods_bitmask):
    try:
        mods_bitmask = int(mods_bitmask)
    except (TypeError, ValueError):
        return "NM"
    mods_map = {1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD", 1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX", 1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AT", 1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K", 1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K", 1 << 20: "FI", 1 << 21: "RD", 1 << 22: "LM", 1 << 23: "CN"}
    readable = [name for bit, name in mods_map.items() if mods_bitmask & bit]
    if "NC" in readable and "DT" in readable:
        readable.remove("DT")
    return "+".join(readable) if readable else "NM"


@inspector_bp.route("/inspector", methods=["GET", "POST"])
def inspector_index():
    user_data = None
    error = None
    mode = 0
    submode = 0
    username = ""
    is_online = False
    current_action = None
    top_scores = []
    server = request.form.get("server", request.args.get("server", "okayu"))
    if request.method == "POST":
        enforce_rate_limit("inspector-search", 30, 60)
        username = (request.form.get("username") or "").strip()[:64]
        try:
            mode = int(request.form.get("mode", 0))
            if mode not in MODES:
                mode = 0
        except (TypeError, ValueError):
            mode = 0
        server = request.form.get("server", "okayu")
        try:
            submode = int(request.form.get("submode", 0)) if server == "okayu" else 0
            if submode not in SUBMODES_OKAYU:
                submode = 0
        except (TypeError, ValueError):
            submode = 0
        if username:
            if server == "okayu":
                user_data = get_osu_user_okayu(username)
                if user_data:
                    is_online, current_action = get_player_status_okayu(username)
                    top_scores = get_top_scores_okayu(username, mode + submode, 5)
            elif server == "bancho":
                user_data = get_osu_user_bancho(username, mode)
                if user_data:
                    top_scores = get_top_scores_bancho(username, mode, 5)
            else:
                error = "Invalid server selection."
            if not user_data and not error:
                error = f"Player '{username}' not found on {server.upper()} server."
        else:
            error = "Please enter a username."
    user_stats = None
    if user_data and isinstance(user_data.get("stats"), dict):
        user_stats = user_data["stats"].get(str(mode), user_data["stats"].get(mode, {}))
    return render_template(
        "inspector.html", user=user_data, user_stats=user_stats, error=error, mode=mode,
        submode=submode, username=username, current_mode=MODES.get(mode, "osu"),
        is_online=is_online, current_action=current_action, top_scores=top_scores,
        server=server, submode_options=SUBMODES_OKAYU, session_user=session.get("user"),
    )


@inspector_bp.route("/inspector/replay/available")
def replay_available():
    enforce_rate_limit("replay-availability", 30, 60)
    server = request.args.get("server", "okayu")
    score_id = request.args.get("score_id", type=int)
    if not score_id or score_id < 1 or server != "okayu":
        return jsonify({"available": False})
    now = time.monotonic()
    cache_key = (server, score_id)
    with _availability_lock:
        cached = _availability_cache.get(cache_key)
        if cached and cached[0] > now:
            return jsonify({"available": cached[1]})
    available = False
    try:
        response = requests.get(f"https://api.osuokayu.pw/v1/get_replay", params={"id": score_id}, timeout=(3, 8), stream=True)
        available = response.status_code == 200 and next(response.iter_content(chunk_size=1), b"") != b""
        response.close()
    except requests.RequestException as error:
        logger.warning("Replay availability check failed: %s", type(error).__name__)
    with _availability_lock:
        _availability_cache[cache_key] = (now + 60, available)
        if len(_availability_cache) > 5000:
            _availability_cache.clear()
    return jsonify({"available": available})


@inspector_bp.route("/inspector/replay/<server>/<int:score_id>")
def download_replay(server, score_id):
    enforce_rate_limit("replay-download", 10, 3600)
    if server not in {"bancho", "okayu"} or score_id < 1:
        return "Replay unavailable.", 404
    headers = {}
    if server == "bancho":
        token = get_bancho_token()
        if not token:
            return "Replay unavailable.", 404
        mode = request.args.get("mode", type=int)
        mode_str = MODES.get(mode, "osu")
        download_url = f"https://osu.ppy.sh/api/v2/scores/{mode_str}/{score_id}/download"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/octet-stream"}
    else:
        download_url = "https://api.osuokayu.pw/v1/get_replay"
    try:
        response = requests.get(download_url, headers=headers, params={"id": score_id} if server == "okayu" else None, timeout=(5, 30), stream=True)
        if server == "bancho" and response.status_code == 404:
            response.close()
            response = requests.get(f"https://osu.ppy.sh/scores/{score_id}/download", timeout=(5, 30), stream=True)
        if response.status_code != 200:
            response.close()
            return "Replay unavailable.", 404
        def generate():
            try:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                response.close()
        return Response(generate(), mimetype="application/x-osu-replay", headers={"Content-Disposition": f"attachment; filename=replay_{score_id}.osr", "X-Content-Type-Options": "nosniff"})
    except requests.RequestException as error:
        logger.warning("Replay download failed: %s", type(error).__name__)
        return "Replay unavailable.", 404
