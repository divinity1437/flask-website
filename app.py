import os
from flask import Flask, jsonify, render_template, request

from config import DOMAIN, MAX_UPLOAD_BYTES, OKAYU_API_URL, OKAYU_AVATAR_URL, secret_key
from security import csrf_token, validate_csrf
from routes.home import home_bp
from routes.inspector import inspector_bp
from routes.circleguard import circleguard_bp
from routes.auth import auth_bp
from routes.donations import donations_bp, start_goal_listener


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=secret_key(),
        OWNER_FIRST_NAME=os.environ.get("OWNER_FIRST_NAME", ""),
        OWNER_LAST_NAME=os.environ.get("OWNER_LAST_NAME", ""),
        OWNER_ALIAS=os.environ.get("OWNER_ALIAS", ""),
        ENABLE_DONATION_LISTENER=os.environ.get("ENABLE_DONATION_LISTENER", "true").lower() == "true",
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024,
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)
    app.register_blueprint(home_bp)
    app.register_blueprint(inspector_bp)
    app.register_blueprint(circleguard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(donations_bp)

    @app.before_request
    def csrf_guard():
        validate_csrf()

    @app.context_processor
    def inject_common():
        return {
            "csrf_token": csrf_token,
            "common": {
                "first_name": app.config.get("OWNER_FIRST_NAME", ""),
                "last_name": app.config.get("OWNER_LAST_NAME", ""),
                "alias": app.config.get("OWNER_ALIAS", ""),
                "domain": DOMAIN,
                "api_url": OKAYU_API_URL,
                "avatar_url": OKAYU_AVATAR_URL,
            },
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            f"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://osu.ppy.sh {OKAYU_API_URL}; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://osu.ppy.sh https://www.donationalerts.com",
        )
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.errorhandler(404)
    def page_not_found(error):
        return render_template("404.html"), 404

    @app.errorhandler(413)
    def payload_too_large(error):
        if request.path.startswith("/circleguard"):
            return jsonify({"error": "Uploaded file exceeds the size limit"}), 413
        return "Request too large", 413

    @app.errorhandler(429)
    def too_many_requests(error):
        return jsonify({"error": "Too many requests"}), 429

    if app.config.get("ENABLE_DONATION_LISTENER", os.environ.get("ENABLE_DONATION_LISTENER", "true").lower() == "true") and not app.testing:
        start_goal_listener(app)
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("FLASK_HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5120")), debug=False)
