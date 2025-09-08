import requests
from flask import Blueprint, render_template, request

inspector_bp = Blueprint('inspector', __name__, template_folder='../templates')

MODES = {
    0: "osu!",
    1: "Taiko",
    2: "Catch",
    3: "Mania",
    4: "osu!std+mod",  # пример для других режимов, если есть
}

def get_osu_user(username):
    """Get player info from Okayu API"""
    url = f"https://api.okayu.click/v1/get_player_info?name={username}&scope=all"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success" and "player" in data:
                return data["player"]
        return None
    except Exception as e:
        print("Request failed:", e)
        return None

def get_player_status(username):
    url = f"https://api.okayu.click/v1/get_player_status?name={username}"
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get("status") != "success":
            return False, None
        
        player_status = data.get("player_status")
        if not player_status:
            return False, None

        is_online = player_status.get("online", False)
        last_seen = player_status.get("last_seen")  # можно использовать как current_action
        return is_online, last_seen

    except Exception as e:
        print(f"Ошибка при запросе статуса игрока: {e}")
        return False, None

def get_top_scores(username, limit=5):
    url = f"https://api.okayu.click/v1/get_player_scores?name={username}&scope=best&limit={limit}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return data.get("scores", [])
    except Exception as e:
        print("Error fetching top scores:", e)
    return []

@inspector_bp.route("/inspector", methods=["GET", "POST"])
def inspector():
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

            is_online, current_action = get_player_status(username)
            top_scores = get_top_scores(username)
        else:
            error = "Please enter a username."

    current_mode_name = MODES.get(mode, "osu!")

    return render_template(
        "inspector.html",
        user=user_data,
        error=error,
        mode=mode,
        username=username,
        current_mode=current_mode_name,
        is_online=is_online,
        current_action=current_action,
        top_scores=top_scores
    )

