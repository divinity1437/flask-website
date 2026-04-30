import requests
from flask import Blueprint, render_template, request

inspector_bp = Blueprint('inspector', __name__, template_folder='../templates')

MODES = {
    0: "osu!",
    1: "Taiko",
    2: "Catch",
    3: "Mania",
}

def get_osu_user(username):
    """Get player info from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_info?name={username}&scope=all"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and "player" in data:
                player = data["player"]
                # Добавляем level в статистику каждого режима, если его нет
                if "stats" in player:
                    for mode_key, stats in player["stats"].items():
                        if "level" not in stats or stats["level"] is None:
                            # Рассчитываем примерный уровень на основе total_score
                            total_score = stats.get("total_score", 0)
                            if total_score > 0:
                                # Формула уровня в osu! (приблизительная)
                                stats["level"] = int(total_score ** 0.4 * 0.2)
                            else:
                                stats["level"] = 1
                return player
        return None
    except Exception as e:
        print("Request failed:", e)
        return None

def get_player_status(username):
    """Get player online status"""
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
        print(f"Ошибка при запросе статуса игрока: {e}")
        return False, None

def get_top_scores(username, limit=5):
    """Get top scores for player"""
    url = f"https://api.okayu.click/v1/get_player_scores?name={username}&scope=best&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            scores = data.get("scores", [])
            # Добавляем readable моды для каждого скора
            for score in scores:
                if "mods" in score:
                    score["mods_readable"] = mods_to_readable(score.get("mods", 0))
                # Добавляем beatmapset_id для фона
                if "beatmap" in score:
                    score["beatmapset_id"] = score["beatmap"].get("beatmapset_id", 0)
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
        1 << 24: "TP", 1 << 25: "KZ", 1 << 26: "1K", 1 << 27: "3K",
        1 << 28: "2K", 1 << 29: "V2", 1 << 30: "MR"
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

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        try:
            mode = int(request.form.get("mode", 0))
        except ValueError:
            mode = 0

        if username:
            user_data = get_osu_user(username)
            if not user_data:
                error = f"Player '{username}' not found or API error."
            else:
                is_online, current_action = get_player_status(username)
                top_scores = get_top_scores(username)
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
        top_scores=top_scores
    )