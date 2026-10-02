from flask import Blueprint, render_template

home_bp = Blueprint('home', __name__, template_folder='../templates')

common = {
    'first_name': 'OwOuser',
    'last_name': 'A.K.A MyAngelAkia',
    'alias': 'OwOuser',
    'domain': 'osuokayu.pw'
}

@home_bp.route('/')
def index():
    return render_template('home.html', common=common)


@home_bp.route('/donationgoals')
def donation_goals():
    return render_template('donationgoals.html')
