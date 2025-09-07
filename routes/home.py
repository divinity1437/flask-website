from flask import Blueprint, render_template

home_bp = Blueprint('home', __name__, template_folder='../templates')

common = {
    'first_name': 'OwOuser',
    'last_name': 'A.K.A MyAngelAkia',
    'alias': 'OwOuser',
    'domain': 'okayu.click'
}

@home_bp.route('/')
def index():
    return render_template('home.html', common=common)