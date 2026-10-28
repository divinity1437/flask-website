import json
import logging
import os
import statistics
import uuid
from pathlib import Path

import requests
from circleguard import Circleguard, ReplayPath
from flask import Blueprint, current_app, jsonify, render_template, request
from werkzeug.utils import secure_filename

from config import BASE_DIR, INSTANCE_DIR, MAX_UPLOAD_BYTES
from security import enforce_rate_limit

logger = logging.getLogger(__name__)
circleguard_bp = Blueprint("circleguard", __name__, template_folder="../templates")
UPLOAD_FOLDER = INSTANCE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(mode=0o700, parents=True, exist_ok=True)

try:
    import redis

    redis_client = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=int(os.environ.get("REDIS_PORT", "6379")), socket_connect_timeout=1, socket_timeout=2, decode_responses=True)
    redis_client.ping()
except Exception:
    redis_client = None
    logger.info("Replay cache unavailable")


def fetch_beatmap_direct(beatmap_id):
    try:
        response = requests.get(f"https://osu.direct/api/v2/b/{int(beatmap_id)}", timeout=(3, 8), headers={"User-Agent": "osu-tools/1.0"})
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
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
            "beatmapset_id": int(data["beatmapset_id"]) if data.get("beatmapset_id") else None,
            "beatmap_id": int(beatmap_id),
        }
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        logger.warning("Beatmap lookup failed: %s", type(error).__name__)
        return None


def fetch_beatmapset_direct(beatmapset_id):
    try:
        response = requests.get(f"https://osu.direct/api/v2/s/{int(beatmapset_id)}", timeout=(3, 8), headers={"User-Agent": "osu-tools/1.0"})
        if response.status_code != 200:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
        return {
            "artist": data.get("artist"),
            "title": data.get("title"),
            "creator": data.get("creator"),
            "beatmapset_id": int(beatmapset_id),
        }
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        logger.warning("Beatmapset lookup failed: %s", type(error).__name__)
        return None


def analyze_replay(file_path):
    cg = Circleguard(os.environ.get("Circleguard"))
    replay = ReplayPath(str(file_path))
    cg.load(replay)
    raw_frametimes = cg.frametimes(replay)
    frametimes = [float(value) for value in raw_frametimes] if raw_frametimes is not None else []
    if frametimes:
        mean_frametime = statistics.mean(frametimes)
        deviation = statistics.pstdev(frametimes)
        coefficient = deviation / (mean_frametime or 1)
        suspicious = coefficient < 0.01
    else:
        mean_frametime = 0
        coefficient = None
        suspicious = False
    snaps = []
    for index, snap in enumerate(cg.snaps(replay, max_angle=12, min_distance=6)):
        angle = float(snap.angle)
        distance = float(snap.distance)
        severity = "danger" if angle < 3 or distance < 3 else "warning" if angle < 7 or distance < 7 else "ok"
        snaps.append({"frame": index, "angle": angle, "distance": distance, "severity": severity})
    beatmap = fetch_beatmap_direct(replay.beatmap_id)
    beatmapset_id = beatmap.get("beatmapset_id") if beatmap else None
    return {
        "username": replay.username,
        "beatmap_id": replay.beatmap_id,
        "mods": str(replay.mods),
        "score": replay.score,
        "ur": float(cg.ur(replay)),
        "frametime": mean_frametime,
        "frametime_cv": coefficient,
        "frametime_suspicious": suspicious,
        "frametimes_list": frametimes,
        "snaps": snaps,
        "snaps_count": len(snaps),
        "beatmap": beatmap,
        "beatmapset": fetch_beatmapset_direct(beatmapset_id) if beatmapset_id else None,
    }


@circleguard_bp.route("/circleguard", methods=["GET", "POST"])
def circleguard_upload():
    if request.method == "GET":
        return render_template("circleguard-upload.html")
    enforce_rate_limit("replay-upload", 5, 3600)
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "A replay file is required"}), 400
    if not uploaded.filename.lower().endswith(".osr"):
        return jsonify({"error": "Only .osr files are accepted"}), 400
    filename = secure_filename(uploaded.filename)
    if not filename:
        return jsonify({"error": "Invalid filename"}), 400
    file_path = UPLOAD_FOLDER / f"{uuid.uuid4().hex}.osr"
    try:
        uploaded.save(file_path)
        if file_path.stat().st_size == 0 or file_path.stat().st_size > MAX_UPLOAD_BYTES:
            return jsonify({"error": "Invalid replay size"}), 400
        with file_path.open("rb") as replay_file:
            if replay_file.read(1) not in (b"\x00", b"\x01", b"\x02", b"\x03"):
                return jsonify({"error": "Invalid replay file"}), 400
        try:
            replay_data = analyze_replay(file_path)
        except Exception as error:
            logger.warning("Replay analysis failed: %s", type(error).__name__)
            return jsonify({"error": "Replay could not be analyzed"}), 422
        if redis_client is not None:
            cache_id = str(uuid.uuid4())
            try:
                redis_client.setex(f"replay:{cache_id}", 3600, json.dumps(replay_data, separators=(",", ":")))
                replay_data["cache_id"] = cache_id
            except Exception as error:
                logger.warning("Replay cache write failed: %s", type(error).__name__)
        return render_template("circleguard.html", replay=replay_data)
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Temporary replay cleanup failed")


@circleguard_bp.route("/circleguard/api/frametimes/<cache_id>")
def get_frametimes_api(cache_id):
    try:
        cache_id = str(uuid.UUID(cache_id))
    except (ValueError, AttributeError):
        return jsonify({"error": "Not found"}), 404
    if redis_client is None:
        return jsonify({"error": "Not found"}), 404
    try:
        cached = redis_client.get(f"replay:{cache_id}")
        if not cached:
            return jsonify({"error": "Not found"}), 404
        replay_data = json.loads(cached)
    except Exception as error:
        logger.warning("Replay cache read failed: %s", type(error).__name__)
        return jsonify({"error": "Not found"}), 404
    return jsonify({"frametimes": replay_data.get("frametimes_list", []), "ur": replay_data.get("ur")})
