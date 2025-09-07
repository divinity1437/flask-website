import os
import statistics as stats
from flask import Blueprint, request, render_template, jsonify
from werkzeug.utils import secure_filename
from circleguard import Circleguard, ReplayPath

UPLOAD_FOLDER = "uploads"

circleguard_bp = Blueprint('circleguard', __name__, template_folder='../templates')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
cg = Circleguard(os.environ.get("Circleguard"))

def fetch_beatmap_direct(beatmap_id: int):
    import requests
    try:
        url = f"https://osu.direct/api/v2/b/{beatmap_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
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

def fetch_beatmapset_direct(beatmapset_id: int):
    import requests
    try:
        url = f"https://osu.direct/api/v2/s/{beatmapset_id}"
        headers = {"User-Agent": "Mozilla/5.0"}
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

@circleguard_bp.route('/circleguard', methods=['GET', 'POST'])
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

    replay_data = {}

    try:
        cg = Circleguard(os.environ.get("Circleguard"))

        replay = ReplayPath(file_path)
        cg.load(replay)

        replay_data = {
            "username": replay.username,
            "beatmap_id": replay.beatmap_id,
            "mods": replay.mods,
            "score": replay.score,
            "ur": cg.ur(replay),
            "frametime": cg.frametime(replay),
            "snaps": [
                {"angle": float(s.angle), "distance": float(s.distance)}
                for s in cg.snaps(replay, max_angle=12, min_distance=6)
            ],
        }

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

        beatmap_info = fetch_beatmap_direct(replay.beatmap_id)
        replay_data["beatmap"] = beatmap_info
        beatmapset_id = beatmap_info.get("beatmapset_id") if beatmap_info else None
        if beatmapset_id:
            replay_data["beatmapset"] = fetch_beatmapset_direct(beatmapset_id)
        else:
            replay_data["beatmapset"] = None

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    return render_template("circleguard.html", replay=replay_data)