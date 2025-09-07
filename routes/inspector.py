import os
import requests
from flask import Blueprint, render_template, request

inspector_bp = Blueprint('inspector', __name__, template_folder='../templates')

def get_osu_user(username, mode=0):
    url = "https://osu.ppy.sh/api/get_user"
    params = {
        "k": os.environ.get("Circleguard"),
        "u": username,
        "type": "string",
        "m": mode
    }

    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
    except Exception as e:
        print("error API request:", e)
        return None

    if not isinstance(data, list) or len(data) == 0:
        print(f"Player '{username}' not found or api error.")
        return None

    return data[0]


@inspector_bp.route("/inspector", methods=["GET", "POST"])
def inspector():
    MODES = {0: "osu!", 1: "Taiko", 2: "Catch the Beat", 3: "Mania"}

    user_data = None
    error = None
    mode = 0
    username = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        try:
            mode = int(request.form.get("mode", 0))
        except ValueError:
            mode = 0

        if username:
            user_data = get_osu_user(username, mode)
            if not user_data:
                error = f"Player '{username}' not found or request error."
        else:
            error = "Type a username."

    current_mode_name = MODES.get(mode, "osu!")

    return render_template(
        "inspector.html",
        user=user_data,
        error=error,
        mode=mode,
        username=username,
        current_mode=current_mode_name
    )
