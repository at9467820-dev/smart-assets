from flask import Blueprint
allocations_bp = Blueprint("allocations", __name__)
from app.blueprints.allocations import routes  # noqa
