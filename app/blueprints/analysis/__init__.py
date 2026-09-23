from flask import Blueprint
analysis_bp = Blueprint("analysis", __name__)
from app.blueprints.analysis import routes  # noqa
