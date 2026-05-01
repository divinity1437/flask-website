import requests
from flask import Blueprint, render_template, request, session
import time
import os

inspector_bp = Blueprint('inspector', __name__, template_folder='../templates')

MODES = {
    0: "osu",
    1: "taiko",
    2: "fruits",
    3: "mania",
}

SUBMODES_OKAYU = {
    0: {"name": "Vanilla", "icon": "🎯", "description": "Standard gameplay"},
    4: {"name": "Relax", "icon": "😌", "description": "Auto-aim, manual tap"},
    8: {"name": "Autopilot", "icon": "🤖", "description": "Auto-tap, manual aim"},
}

DEFAULT_SUBMODE = 0

bancho_token = None
token_expiry = 0

def get_bancho_token():
    """Получает или обновляет access-токен для Bancho API"""
    global bancho_token, token_expiry
    
    # Если токен ещё живой (обычно живёт 1-2 часа)
    if bancho_token and time.time() < token_expiry:
        return bancho_token
    
    # Получаем новый токен
    client_id = os.environ.get("OSU_CLIENT_ID")
    client_secret = os.environ.get("OSU_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Bancho API: missing credentials")
        return None
    
    url = "https://osu.ppy.sh/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "public"
    }
    
    try:
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token_data = response.json()
            bancho_token = token_data.get("access_token")
            token_expiry = time.time() + 5400  # 1.5 часа
            return bancho_token
        else:
            print(f"Token error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Token request failed: {e}")
        return None

def get_osu_user_bancho(username, mode=0):
    """Get player info from official osu! API v2 (Bancho)"""
    token = get_bancho_token()
    if not token:
        return None
    
    mode_str = MODES.get(mode, "osu")
    url = f"https://osu.ppy.sh/api/v2/users/@{username}/{mode_str}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return transform_bancho_data(data, mode)
        elif response.status_code == 404:
            print(f"User '{username}' not found on Bancho")
            return None
        else:
            print(f"Bancho API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Bancho API request failed: {e}")
        return None

def transform_bancho_data(bancho_user, mode):
    """Преобразует данные из Bancho API в формат, который ожидает шаблон"""
    stats = bancho_user.get("statistics", {})
    
    mode_stats = {
        "pp": round(stats.get("pp", 0)),
        "rank": stats.get("global_rank", 0),
        "country_rank": stats.get("country_rank", 0),
        "acc": round(stats.get("hit_accuracy", 0), 2),
        "plays": stats.get("play_count", 0),
        "total_score": stats.get("total_score", 0),
        "total_hits": stats.get("total_hits", 0),
        "level": int(stats.get("level", {}).get("current", 1)) if stats.get("level") else 1,
        "counts_ss": stats.get("grade_counts", {}).get("ss", 0),
        "counts_s": stats.get("grade_counts", {}).get("s", 0),
        "counts_a": stats.get("grade_counts", {}).get("a", 0),
    }
    
    # Прогресс PP
    current_pp = mode_stats["pp"]
    rank = mode_stats["rank"]
    if rank and rank < 10000:
        progress = min(100, (current_pp % 1000) / 10)
    else:
        progress = 50
    mode_stats["pp_progress"] = progress
    
    # Получаем баннер (cover)
    cover_url = None
    cover = bancho_user.get("cover")
    if cover:
        cover_url = cover.get("url")
    
    # Получаем аватар
    avatar_url = bancho_user.get("avatar_url")
    
    return {
        "info": {
            "id": bancho_user.get("id"),
            "name": bancho_user.get("username"),
            "country": bancho_user.get("country", {}).get("code", ""),
            "country_code": bancho_user.get("country", {}).get("code", ""),
            "cover_url": cover_url,
            "avatar_url": avatar_url
        },
        "stats": {str(mode): mode_stats}
    }

def get_osu_user_okayu(username):
    """Get player info from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_info?name={username}&scope=all"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and "player" in data:
                player = data["player"]
                
                # Добавляем уровень, если нет
                if "stats" in player:
                    for mode_key, stats in player["stats"].items():
                        if "level" not in stats or stats["level"] is None:
                            total_score = stats.get("total_score", 0)
                            if total_score > 0:
                                stats["level"] = int(total_score ** 0.4 * 0.2)
                            else:
                                stats["level"] = 1
                
                # Добавляем баннер для Okayu
                if "info" in player:
                    user_id = player["info"].get("id")
                    if user_id:
                        player["info"]["cover_url"] = f"https://okayu.click/banners/{user_id}"
                        # Аватар для Okayu
                        player["info"]["avatar_url"] = f"https://a.okayu.click/{user_id}"
                
                return player
        return None
    except Exception as e:
        print("Okayu API error:", e)
        return None

def get_player_status_okayu(username):
    """Get player online status from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_status?name={username}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get("status") != "success":
            return False, None
        
        player_status = data.get("player_status")
        if not player_status:
            return False, None

        is_online = player_status.get("online", False)
        last_seen = player_status.get("last_seen")
        return is_online, last_seen

    except Exception as e:
        print(f"Error fetching player status: {e}")
        return False, None

def get_top_scores_okayu(username, mode=0, limit=5):
    """Get top scores from Okayu API with mode support"""
    mode_map = {0: "osu", 1: "taiko", 2: "catch", 3: "mania"}
    mode_str = mode_map.get(mode, "osu")
    
    url = f"https://api.okayu.click/v1/get_player_scores?name={username}&scope=best&limit={limit}&mode={mode_str}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            scores = data.get("scores", [])
            for score in scores:
                if "mods" in score:
                    score["mods_readable"] = mods_to_readable(score.get("mods", 0))
            return scores
    except Exception as e:
        print("Error fetching top scores from Okayu:", e)
    return []

def get_top_scores_bancho(username, mode=0, limit=5):
    """Get top scores from Bancho API with mode support"""
    token = get_bancho_token()
    if not token:
        return []
    
     mode_map = {0: "osu", 1: "taiko", 2: "fruits", 3: "mania"}
    mode_str = mode_map.get(mode, "osu")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        user_url = f"https://osu.ppy.sh/api/v2/users/@{username}"
        user_resp = requests.get(user_url, headers=headers, timeout=10)
        if user_resp.status_code != 200:
            return []
        
        user_id = user_resp.json().get("id")
        if not user_id:
            return []
        
        scores_url = f"https://osu.ppy.sh/api/v2/users/{user_id}/scores/best"
        params = {"limit": limit, "mode": mode_str}
        
        scores_resp = requests.get(scores_url, headers=headers, params=params, timeout=10)
        if scores_resp.status_code == 200:
            scores = scores_resp.json()
            for score in scores:
                mods_list = score.get("mods", [])
                score["mods_readable"] = "+".join(mods_list) if mods_list else "NM"
                if "beatmap" in score:
                    score["beatmapset_id"] = score["beatmap"].get("beatmapset_id", 0)
            return scores
    except Exception as e:
        print(f"Bancho top scores error for mode {mode_str}: {e}")
    
    return []

def mods_to_readable(mods_bitmask):
    """Convert mods bitmask to readable string (для Okayu API)"""
    mods_map = {
        1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
        1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
        1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AT",
        1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
        1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
        1 << 20: "FI", 1 << 21: "RD", 1 << 22: "LM", 1 << 23: "CN",
    }
    
    readable = []
    for bit, name in mods_map.items():
        if mods_bitmask & bit:
            if name == "NC" and "DT" in readable:
                readable.remove("DT")
            readable.append(name)
    
    return "+".join(readable) if readable else "NM"

@inspector_bp.route("/inspector", methods=["GET", "POST"])
def inspector_index():
    user_data = None
    error = None
    mode = 0
    submode = 0  # Добавляем подрежим
    username = ""
    is_online = False
    current_action = None
    top_scores = []
    server = request.form.get("server", request.args.get("server", "okayu"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        try:
            mode = int(request.form.get("mode", 0))
        except ValueError:
            mode = 0
        # Получаем подрежим (только для Okayu)
        submode = int(request.form.get("submode", 0)) if server == "okayu" else 0
        server = request.form.get("server", "okayu")

        if username:
            if server == "okayu":
                # Для Okayu используем mode + submode
                actual_mode = mode + submode  # 0+0=0, 0+4=4, 0+8=8
                user_data = get_osu_user_okayu(username)
                if user_data:
                    is_online, current_action = get_player_status_okayu(username)
                    top_scores = get_top_scores_okayu(username, actual_mode, 5)
            elif server == "bancho":
                # Для Bancho игнорируем submode
                user_data = get_osu_user_bancho(username, mode)
                if user_data:
                    is_online = False
                    top_scores = get_top_scores_bancho(username, mode, 5)
            
            if not user_data:
                error = f"Player '{username}' not found on {server.upper()} server."
        else:
            error = "Please enter a username."

    current_mode_name = MODES.get(mode, "osu")

    user_stats = None
    if user_data and "stats" in user_data:
        user_stats = user_data["stats"].get(str(mode), user_data["stats"].get(mode, {}))

    return render_template(
        "inspector.html",
        user=user_data,
        user_stats=user_stats,
        error=error,
        mode=mode,
        submode=submode,
        username=username,
        current_mode=current_mode_name,
        is_online=is_online,
        current_action=current_action,
        top_scores=top_scores,
        server=server,
        submode_options=SUBMODES_OKAYU if server == "okayu" else {},
        session_user=session.get('user')
    )