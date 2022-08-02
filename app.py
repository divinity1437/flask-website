import io
import json
import os
import re
import requests
import json

from flask import *
from flask_hcaptcha import hCaptcha
from typing import Dict
from discord import Webhook, RequestsWebhookAdapter
from markupsafe import Markup

webhook = Webhook.partial(998476036620685362, 'kO8LXD36-ATSJWt9cU5V6XQbF0Irqci18mpsvD9jZW56bre0Vo4LXsbdk4RHeh8heABb', adapter=RequestsWebhookAdapter())
app = Flask(__name__)
hcaptcha = hCaptcha(app)
HCAPTCHA_ENABLED = True
HCAPTCHA_SITE_KEY = "930d77f0-2a8d-4878-9390-cb0fbbc4f9fb"
HCAPTCHA_SECRET_KEY = "0x57cc8344CEE0248B2EeeB1bDa25DE279883d80f6"

common = {
    'first_name': 'OwOuser',
    'last_name': 'A.K.A morgn',
    'alias': 'OwOuser#9860'
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

    return render_template('sharex.html', common=common, shibe=shibe_aa, filecount=filecount)

@app.route('/mail', methods=['GET', 'POST'])
def mail():
    message = ''
    if request.method == 'GET':
        email = request.form.get('email')
        discord = request.form.get('discord')
    if request.method == 'POST':
        email = request.form.get('email')
        discord = request.form.get('discord')
        if re.fullmatch(regex, email) and re.fullmatch(regex2, discord) and hcaptcha.verify():
            message = "Your request was successfully send. For fast response, write me in discord: OwOuser#9860"
            webhook.send(discord + ' requested for ' + email, username='dr.dre')
        else:
            message = "I guess you made a typo. Please, check again discord and email fields."

    return render_template('mail.html', message=message, common=common)


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
    app.run(host="127.0.0.1", debug=True)
