import os
import statistics as stats
import uuid
import pickle
from flask import Blueprint, request, render_template, jsonify
from werkzeug.utils import secure_filename
from circleguard import Circleguard, ReplayPath
import requests

# Попробуем импортировать redis, если нет - работаем без кэша
try:
    import redis
    r = redis.Redis(host='localhost', port=6379, decode_responses=False)
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False
    print("Redis not available, caching disabled")

UPLOAD_FOLDER = "uploads"
circleguard_bp = Blueprint('circleguard', __name__, template_folder='../templates')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def fetch_beatmap_direct(beatmap_id: int):
    """Получение информации о карте через osu.direct"""
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
    """Получение информации о сете карт"""
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

def analyze_replay(file_path):
    """Анализ риплея и возврат всех данных"""
    cg = Circleguard(os.environ.get("Circleguard"))
    replay = ReplayPath(file_path)
    cg.load(replay)
    
    # Получаем frametimes для графика
    frametimes_raw = cg.frametimes(replay)
    frametimes_list = [float(x) for x in frametimes_raw] if frametimes_raw else []
    
    # Статистика по frametimes
    if frametimes_list:
        mean_ft = stats.mean(frametimes_list)
        stdev_ft = stats.pstdev(frametimes_list)
        cv = stdev_ft / (mean_ft or 1)
        frametime_suspicious = cv < 0.01
    else:
        mean_ft = 0
        cv = None
        frametime_suspicious = False
    
    # Получаем snaps с дополнительной информацией
    snaps_raw = cg.snaps(replay, max_angle=12, min_distance=6)
    snaps = []
    for i, s in enumerate(snaps_raw):
        snaps.append({
            "frame": i,
            "angle": float(s.angle),
            "distance": float(s.distance),
            "severity": "danger" if s.angle < 3 or s.distance < 3 else 
                       "warning" if s.angle < 7 or s.distance < 7 else "ok"
        })
    
    replay_data = {
        "username": replay.username,
        "beatmap_id": replay.beatmap_id,
        "mods": replay.mods,
        "score": replay.score,
        "ur": cg.ur(replay),
        "frametime": mean_ft,
        "frametime_cv": cv,
        "frametime_suspicious": frametime_suspicious,
        "frametimes_list": frametimes_list,  # для графика
        "snaps": snaps,
        "snaps_count": len(snaps)
    }
    
    # Получаем информацию о карте
    beatmap_info = fetch_beatmap_direct(replay.beatmap_id)
    replay_data["beatmap"] = beatmap_info
    beatmapset_id = beatmap_info.get("beatmapset_id") if beatmap_info else None
    if beatmapset_id:
        replay_data["beatmapset"] = fetch_beatmapset_direct(beatmapset_id)
    else:
        replay_data["beatmapset"] = None
    
    return replay_data

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
    
    try:
        replay_data = analyze_replay(file_path)
        
        # Кэшируем результат в Redis если доступен
        if REDIS_AVAILABLE:
            cache_id = str(uuid.uuid4())
            r.setex(f"replay:{cache_id}", 3600, pickle.dumps(replay_data))
            replay_data["cache_id"] = cache_id
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
    
    return render_template("circleguard.html", replay=replay_data)

@circleguard_bp.route('/circleguard/api/frametimes/<cache_id>')
def get_frametimes_api(cache_id):
    """API для получения frametimes для графика"""
    if REDIS_AVAILABLE:
        data = r.get(f"replay:{cache_id}")
        if data:
            replay_data = pickle.loads(data)
            return jsonify({
                "frametimes": replay_data.get("frametimes_list", []),
                "ur": replay_data.get("ur")
            })
    return jsonify({"error": "Not found"}), 404