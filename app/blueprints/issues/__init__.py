from flask import Blueprint

issues_bp = Blueprint("issues", __name__)

from app.blueprints.issues import routes
