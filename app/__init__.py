"""
AssetPulse — Application Factory
"""
import os
from flask import Flask, render_template, request
from config import config_map
from app.extensions import db, login_manager, migrate, mail

# ── Resolve frontend paths ──
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
_FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")
_FRONTEND_TEMPLATES = os.path.join(_PROJECT_ROOT, "frontend", "templates")
_FRONTEND_STATIC = os.path.join(_PROJECT_ROOT, "frontend", "static")


def create_app(config_name: str = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    # Serve built React app if dist exists, else fallback to templates
    if os.path.exists(_FRONTEND_DIST):
        app = Flask(
            __name__,
            static_folder=_FRONTEND_DIST,
            static_url_path="",
        )
    else:
        app = Flask(
            __name__,
            template_folder=_FRONTEND_TEMPLATES,
            static_folder=_FRONTEND_STATIC,
        )
    app.config.from_object(config_map[config_name])

    # ── Ensure upload / QR directories exist ──────────────────
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["QR_FOLDER"], exist_ok=True)

    # ── Initialize extensions ──────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # ── User loader ────────────────────────────────────────────
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Register Blueprints ────────────────────────────────────
    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.assets import assets_bp
    from app.blueprints.maintenance import maintenance_bp
    from app.blueprints.issues import issues_bp
    from app.blueprints.orders import orders_bp
    from app.blueprints.budget import budget_bp
    from app.blueprints.reports import reports_bp
    from app.blueprints.allocations import allocations_bp
    from app.blueprints.analysis import analysis_bp
    from app.blueprints.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(assets_bp, url_prefix="/assets")
    app.register_blueprint(maintenance_bp, url_prefix="/maintenance")
    app.register_blueprint(issues_bp, url_prefix="/issues")
    app.register_blueprint(orders_bp, url_prefix="/orders")
    app.register_blueprint(budget_bp, url_prefix="/budget")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(allocations_bp, url_prefix="/allocations")
    app.register_blueprint(analysis_bp, url_prefix="/analysis")
    app.register_blueprint(api_bp, url_prefix="/api")

    # ── Error handlers ─────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api"):
            return {"error": "Forbidden", "status_code": 403}, 403
        try:
            return render_template("errors/403.html"), 403
        except Exception:
            return {"error": "Forbidden"}, 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api"):
            return {"error": "Not Found", "status_code": 404}, 404
        try:
            return render_template("errors/404.html"), 404
        except Exception:
            return {"error": "Not Found"}, 404

    @app.errorhandler(500)
    def server_error(e):
        if request.path.startswith("/api"):
            return {"error": "Internal Server Error", "status_code": 500}, 500
        try:
            return render_template("errors/500.html"), 500
        except Exception:
            return {"error": "Internal Server Error"}, 500

    # ── CORS Support for React SPA ─────────────────────────────
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Requested-With"
        response.headers["Access-Control-Allow-Methods"] = "GET,PUT,POST,DELETE,OPTIONS,PATCH"
        return response

    # ── Context processors ─────────────────────────────────────
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from app.models import MaintenanceLog, Asset, AssetIssue
        from datetime import date, datetime
        alerts = 0
        overdue_issues_count = 0
        if current_user.is_authenticated:
            # Overdue maintenance
            overdue = MaintenanceLog.query.filter(
                MaintenanceLog.status.in_(["pending", "in_progress"]),
                MaintenanceLog.scheduled_date < date.today(),
            ).count()
            # Expiring warranties (next 30 days)
            expiring = Asset.query.filter(
                Asset.warranty_expiry.isnot(None),
                Asset.warranty_expiry <= date.today(),
            ).count()
            # Overdue asset issues / returns
            overdue_issues_count = AssetIssue.query.filter(
                AssetIssue.status == "issued",
                AssetIssue.expected_return_date.isnot(None),
                AssetIssue.expected_return_date < datetime.utcnow(),
            ).count()
            alerts = overdue + expiring + overdue_issues_count
        return dict(
            global_alerts=alerts,
            overdue_issues_count=overdue_issues_count,
            now=datetime.now,
            today=date.today()
        )

    # ── Serve Pure React SPA ───────────────────────────────────
    if os.path.exists(_FRONTEND_DIST):
        from flask import send_from_directory
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_react(path):
            if path.startswith("api/") or path.startswith("qrcodes/") or path.startswith("uploads/"):
                return not_found(404)
            if path != "" and os.path.exists(os.path.join(_FRONTEND_DIST, path)):
                return send_from_directory(_FRONTEND_DIST, path)
            return send_from_directory(_FRONTEND_DIST, "index.html")

    return app
