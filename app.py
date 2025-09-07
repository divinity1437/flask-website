import os
from flask import Flask, render_template
from dotenv import load_dotenv
from routes.home import home_bp
from routes.inspector import inspector_bp
from routes.circleguard import circleguard_bp

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)

app.register_blueprint(home_bp)
app.register_blueprint(inspector_bp)
app.register_blueprint(circleguard_bp)

@app.context_processor
def inject_common():
    return {
        'common': {
            'first_name': 'OwOuser',
            'last_name': 'A.K.A MyAngelAkia',
            'alias': 'OwOuser',
            'domain': 'okayu.click'
        }
    }

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=False)