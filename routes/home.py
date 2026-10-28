from flask import Blueprint, current_app, render_template
from config import DOMAIN

home_bp = Blueprint("home", __name__, template_folder="../templates")


@home_bp.route("/")
def index():
    common = {
        "first_name": current_app.config.get("OWNER_FIRST_NAME", ""),
        "last_name": current_app.config.get("OWNER_LAST_NAME", ""),
        "alias": current_app.config.get("OWNER_ALIAS", ""),
        "domain": DOMAIN,
    }
    return render_template("home.html", common=common)


@home_bp.route("/donationgoals")
def donation_goals():
    return render_template("donationgoals.html")
