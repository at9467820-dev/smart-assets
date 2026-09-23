from flask import Blueprint
maintenance_bp = Blueprint("maintenance", __name__)
from app.blueprints.maintenance import routes  # noqa
