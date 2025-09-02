import io
import json
import os
import re
import requests
import json
import time
import urllib.request
import urllib.error
import socket
import os
import math
import statistics as stats

from os.path import join, dirname
from dotenv import load_dotenv
from flask import *
from flask_recaptcha import ReCaptcha
from datetime import datetime, date
from typing import Dict
from discord import SyncWebhook
from markupsafe import Markup
from werkzeug.utils import secure_filename
from circleguard import *
from pathlib import Path

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)
cg = Circleguard(os.environ.get("Circleguard"))
# replay folder
UPLOAD_FOLDER = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

common = {
    'first_name': 'OwOuser',
    'last_name': 'A.K.A MyAngelAkia',
    'alias': 'OwOuser',
    'domain': 'okayu.click'
}

@app.route('/')
def index():
    return render_template('home.html', common=common)

def fetch_beatmapset_direct(beatmapset_id: int):
    """Получает данные карты через osu.direct API по beatmap_id."""
    try:
        url = f"https://osu.direct/api/v2/s/{beatmapset_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/138.0.0.0 Safari/537.36"
        }
        r = requests.get(url, timeout=8, headers=headers)
        data = r.json()
        if r.status_code == 200:
            return {
                "artist": data.get("artist"),
                "title": data.get("title"),
                "creator": data.get("creator"),
                "beatmapset_id": beatmapset_id
            }
    except Exception as e:
        print("osu.direct API error:", e)
    return None

def fetch_beatmap_direct(beatmap_id: int):
    """Получает данные карты через osu.direct API по beatmap_id."""
    try:
        url = f"https://osu.direct/api/v2/b/{beatmap_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/138.0.0.0 Safari/537.36"
        }
        r = requests.get(url, timeout=8, headers=headers)
        data = r.json()
        if r.status_code == 200:
            return {
                "artist": data.get("artist"),
                "title": data.get("title"),
                "version": data.get("version"),
                "creator": data.get("creator"),
                "bpm": data.get("bpm"),
                "length": data.get("length"),
                "cs": data.get("cs"),
                "ar": data.get("ar"),
                "od": data.get("accuracy"),
                "hp": data.get("drain"),
                "beatmapset_id": data.get("beatmapset_id"),
                "beatmap_id": beatmap_id
            }
    except Exception as e:
        print("osu.direct API error:", e)
    return None

@app.route('/circleguard', methods=['GET', 'POST'])
def circleguard_upload():
    if request.method == 'GET':
        return render_template("circleguard-upload.html")

    if "file" not in request.files:
        return jsonify({"error": "File not found"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    if not f.filename.lower().endswith(".osr"):
        return jsonify({"error": "Only .osr files are allowed"}), 400

    filename = secure_filename(f.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(file_path)

    try:
        cg = Circleguard(os.environ.get("Circleguard"))

        replay = ReplayPath(file_path)
        cg.load(replay)

        # Базовые данные
        replay_data = {
            "username": replay.username,
            "beatmap_id": replay.beatmap_id,
            "mods": replay.mods,
            "score": replay.score,
            "ur": cg.ur(replay),
            "frametime": cg.frametime(replay),
            "snaps": [
                {
                    "angle": float(snap.angle),
                    "distance": float(snap.distance),
                }
                for snap in cg.snaps(replay, max_angle=12, min_distance=6)
            ],
        }

        # frametime анализ
        frametimes = cg.frametimes(replay)
        if frametimes is not None and len(frametimes) > 0:
            ft = [float(x) for x in frametimes]
            mean_ft = stats.mean(ft)
            stdev_ft = stats.pstdev(ft)
            cv = stdev_ft / (mean_ft or 1)
            replay_data["frametime_cv"] = cv
            replay_data["frametime_suspicious"] = cv < 0.01
        else:
            replay_data["frametime_cv"] = None
            replay_data["frametime_suspicious"] = False

        # Загружаем инфу о карте через osu.direct
        beatmap_info = fetch_beatmap_direct(replay.beatmap_id)
        replay_data["beatmap"] = beatmap_info

        # Получаем beatmapset_id из данных карты
        beatmapset_id = beatmap_info.get("beatmapset_id") if beatmap_info else None
        if beatmapset_id:
            beatmapset_info = fetch_beatmapset_direct(beatmapset_id)
            replay_data["beatmapset"] = beatmapset_info
        else:
            replay_data["beatmapset"] = None

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    return render_template("circleguard.html", replay=replay_data)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', common=common), 404


def get_static_file(path):
    site_root = os.path.realpath(os.path.dirname(__file__))
    return os.path.join(site_root, path)

def get_static_json(path):
    return json.load(open(get_static_file(path)))

if __name__ == "__main__":
    print("running py app")
    app.run(host="127.0.0.1", debug=False)
