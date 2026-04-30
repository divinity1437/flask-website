import os
from dotenv import load_dotenv
from flask import Flask, render_template
from routes.home import home_bp
from routes.inspector import inspector_bp
from routes.circleguard import circleguard_bp
from routes.auth import auth_bp

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

print("OSU_CLIENT_ID:", os.environ.get("OSU_CLIENT_ID"))

app = Flask(__name__)

app.register_blueprint(home_bp)
app.register_blueprint(inspector_bp)
app.register_blueprint(circleguard_bp)
app.register_blueprint(auth_bp)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

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
    app.run(host="127.0.0.1", port=5120, debug=False)