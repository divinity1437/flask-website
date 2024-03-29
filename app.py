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

from os.path import join, dirname, getsize
from dotenv import load_dotenv
from flask import *
from flask_recaptcha import ReCaptcha
from datetime import datetime, date
from typing import Dict
from discord import SyncWebhook
from markupsafe import Markup
from werkzeug.utils import secure_filename
from circleguard import *

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)
app.config['RECAPTCHA_SITE_KEY'] = os.environ.get("RECAPTCHA_SITE_KEY")
app.config['RECAPTCHA_SECRET_KEY'] = os.environ.get("RECAPTCHA_SECRET_KEY")
recaptcha = ReCaptcha(app) 
cg = Circleguard(os.environ.get("Circleguard"))

common = {
    'first_name': 'OwOuser',
    'last_name': 'A.K.A morgn',
    'alias': 'OwOuser#9860',
    'domain': 'okayu.me'
}

regex = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')
regex2 = re.compile(r"(?:!\w+\s+)?([\w\s]*#[0-9]*)")

@app.route('/')
def index():
    return render_template('home.html', common=common)

@app.route('/sharex', methods=['GET', 'POST'])
def sharex():
    shibe = requests.get("http://shibe.online/api/shibes?count=1&urls=true&httpsUrls=true").text
    shibe_parsed = json.loads(shibe)
    shibe_aa = shibe_parsed[0]
    
    # Total count of images in dir
    dir_path = r'/home/owo/sharex/images/'
    filecount = 0
    for path in os.listdir(dir_path):
        if os.path.isfile(os.path.join(dir_path, path)):
            filecount += 1
    for root, dirs, files in os.walk('/home/owo/sharex/images/'):
        total_size = sum(getsize(join(root, name)) for name in files)
        print(root, total_size/1024**2)


    return render_template('sharex.html', common=common, shibe=shibe_aa, filecount=filecount, total_size=total_size/1024**2)

@app.route('/circleguard')
def circleguard():
   return render_template('circleguard.html', common=common)
    
@app.route('/circleguard', methods = ['GET', 'POST'])
def circleguard_upload():
    if request.method == 'POST':
        f = request.files['file']
        f.save(secure_filename(f.filename))
        f.filename_underscope = f.filename.replace(" ", "_").replace(']','').replace('[','').replace('(','').replace(')','').replace("'","").replace('!','').replace('~','').replace('&','').replace(',','')
        replay = ReplayPath(r"/root/flask-website/" + f.filename_underscope)
        cg.load(replay)
        print(replay)
        # Getting replay ur, frametime, frametimes and snaps
        replay_ur, replay_frametime, replay_frametimes, replay_snaps = cg.ur(replay), cg.frametime(replay), cg.frametimes(replay), cg.snaps(replay, max_angle=12, min_distance=6)
        # Getting replay info such as bmap, timestamp, username, mods, 300/100/50/miss and score
        r_timestamp, r_beatmap_id, r_username, r_mods, r_count_300, r_count_100, r_count_50, r_count_miss, r_score, r_max_combo = replay.timestamp, replay.beatmap_id, replay.username, replay.mods,replay.count_300, replay.count_100, replay.count_50, replay.count_miss, replay.score, replay.max_combo
        print("replay was loaded and data was displayed, delete file now")
        os.remove(f.filename_underscope)

        return render_template('circleguard-post.html', replay_ur=replay_ur, replay_frametime=replay_frametime, replay_snaps=replay_snaps, r_timestamp=r_timestamp, r_beatmap_id=r_beatmap_id, r_username=r_username, r_mods=r_mods, r_count_300=r_count_300, r_count_100=r_count_100, r_count_50=r_count_50, r_count_miss=r_count_miss, r_score=r_score, r_max_combo=r_max_combo, common=common)

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
