from flask import Blueprint
budget_bp = Blueprint("budget", __name__)
from app.blueprints.budget import routes  # noqa
