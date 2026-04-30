import requests
from flask import Blueprint, render_template, request, session

inspector_bp = Blueprint('inspector', __name__, template_folder='../templates')

MODES = {
    0: "osu!",
    1: "Taiko",
    2: "Catch",
    3: "Mania",
}

def get_osu_user_bancho(username, mode=0):
    """Get player info from official osu! API v2"""
    # Требуется access_token, но пока используем публичное API
    # Временно используем https://osu.ppy.sh/api/get_user?k=API_KEY
    # Для полной интеграции нужно добавить OAuth scope 'public'
    url = f"https://osu.ppy.sh/api/v2/users/{username}/{MODES.get(mode, 'osu')}"
    try:
        return None
    except Exception as e:
        print(f"Bancho API error: {e}")
        return None

def get_osu_user_okayu(username):
    """Get player info from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_info?name={username}&scope=all"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and "player" in data:
                player = data["player"]
                if "stats" in player:
                    for mode_key, stats in player["stats"].items():
                        if "level" not in stats or stats["level"] is None:
                            total_score = stats.get("total_score", 0)
                            if total_score > 0:
                                stats["level"] = int(total_score ** 0.4 * 0.2)
                            else:
                                stats["level"] = 1
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

def get_top_scores_okayu(username, limit=5):
    """Get top scores from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_scores?name={username}&scope=best&limit={limit}"
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
        print("Error fetching top scores:", e)
    return []

def mods_to_readable(mods_bitmask):
    """Convert mods bitmask to readable string"""
    mods_map = {
        1 << 0: "NF", 1 << 1: "EZ", 1 << 2: "TD", 1 << 3: "HD",
        1 << 4: "HR", 1 << 5: "SD", 1 << 6: "DT", 1 << 7: "RX",
        1 << 8: "HT", 1 << 9: "NC", 1 << 10: "FL", 1 << 11: "AT",
        1 << 12: "SO", 1 << 13: "AP", 1 << 14: "PF", 1 << 15: "4K",
        1 << 16: "5K", 1 << 17: "6K", 1 << 18: "7K", 1 << 19: "8K",
        1 << 20: "FI", 1 << 21: "RD", 1 << 22: "LM", 1 << 23: "CN",
        1 << 24: "TP", 1 << 25: "KZ"
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
    username = ""
    is_online = False
    current_action = None
    top_scores = []
    server = request.args.get("server", request.form.get("server", "okayu"))  # okayu или bancho

    if request.method == "GET" and request.args.get("username"):
        username = request.args.get("username")
        server = "bancho"  # Авторизованные пользователи из Bancho
        mode = int(request.args.get("mode", 0))
        
        user_data = get_osu_user_bancho(username, mode)
        if not user_data:
            error = f"Player '{username}' not found on Bancho"
    
    elif request.method == "POST":
        username = (request.form.get("username") or "").strip()
        try:
            mode = int(request.form.get("mode", 0))
        except ValueError:
            mode = 0
        server = request.form.get("server", "okayu")

        if username:
            if server == "okayu":
                user_data = get_osu_user_okayu(username)
                if user_data:
                    is_online, current_action = get_player_status_okayu(username)
                    top_scores = get_top_scores_okayu(username)
            elif server == "bancho":
                user_data = get_osu_user_bancho(username, mode)
            
            if not user_data:
                error = f"Player '{username}' not found on {server.upper()} server."
        else:
            error = "Please enter a username."

    current_mode_name = MODES.get(mode, "osu!")

    user_stats = None
    if user_data and "stats" in user_data:
        user_stats = user_data["stats"].get(str(mode), user_data["stats"].get(mode, {}))

    return render_template(
        "inspector.html",
        user=user_data,
        user_stats=user_stats,
        error=error,
        mode=mode,
        username=username,
        current_mode=current_mode_name,
        is_online=is_online,
        current_action=current_action,
        top_scores=top_scores,
        server=server,
        session_user=session.get('user')
    )