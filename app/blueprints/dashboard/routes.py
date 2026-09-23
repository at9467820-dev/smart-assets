"""
Dashboard Blueprint — Main overview page.
"""
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, timedelta
from app.blueprints.dashboard import dashboard_bp
from app.models import Asset, Department, MaintenanceLog, User, ActivityLog
from app.extensions import db


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    # ── Stat Counts ────────────────────────────────────────────
    if current_user.is_admin:
        total_assets = Asset.query.count()
        active_assets = Asset.query.filter_by(status="active").count()
        under_repair = Asset.query.filter_by(status="under_repair").count()
        damaged = Asset.query.filter_by(status="damaged").count()
        retired = Asset.query.filter_by(status="retired").count()
        pending_maintenance = MaintenanceLog.query.filter_by(status="pending").count()
    else:
        dept_id = current_user.department_id
        total_assets = Asset.query.filter_by(department_id=dept_id).count()
        active_assets = Asset.query.filter_by(department_id=dept_id, status="active").count()
        under_repair = Asset.query.filter_by(department_id=dept_id, status="under_repair").count()
        damaged = Asset.query.filter_by(department_id=dept_id, status="damaged").count()
        retired = Asset.query.filter_by(department_id=dept_id, status="retired").count()
        pending_maintenance = (
            MaintenanceLog.query
            .join(Asset)
            .filter(Asset.department_id == dept_id, MaintenanceLog.status == "pending")
            .count()
        )

    # ── Department breakdown for chart ─────────────────────────
    dept_data = (
        db.session.query(Department.name, func.count(Asset.id))
        .outerjoin(Asset, Asset.department_id == Department.id)
        .group_by(Department.id, Department.name)
        .all()
    )
    dept_labels = [d[0] for d in dept_data]
    dept_counts = [d[1] for d in dept_data]

    # ── Alerts panel ───────────────────────────────────────────
    today = date.today()
    thirty_days = today + timedelta(days=30)

    overdue_logs = (
        MaintenanceLog.query
        .filter(
            MaintenanceLog.status.in_(["pending", "in_progress"]),
            MaintenanceLog.scheduled_date < today,
        )
        .order_by(MaintenanceLog.scheduled_date)
        .limit(5)
        .all()
    )

    expiring_warranties = (
        Asset.query
        .filter(
            Asset.warranty_expiry.isnot(None),
            Asset.warranty_expiry.between(today, thirty_days),
        )
        .order_by(Asset.warranty_expiry)
        .limit(5)
        .all()
    )

    # High-risk assets
    all_assets_for_risk = Asset.query.filter(Asset.status != "retired").limit(100).all()
    high_risk = sorted(
        [a for a in all_assets_for_risk if a.risk_score >= 60],
        key=lambda a: a.risk_score, reverse=True
    )[:5]

    # ── Recent activity ────────────────────────────────────────
    recent_activity = (
        ActivityLog.query
        .order_by(ActivityLog.timestamp.desc())
        .limit(8)
        .all()
    )

    # ── Recent assets ─────────────────────────────────────────
    recent_assets = (
        Asset.query
        .order_by(Asset.created_at.desc())
        .limit(6)
        .all()
    )

    return render_template(
        "dashboard/index.html",
        total_assets=total_assets,
        active_assets=active_assets,
        under_repair=under_repair,
        damaged=damaged,
        retired=retired,
        pending_maintenance=pending_maintenance,
        dept_labels=dept_labels,
        dept_counts=dept_counts,
        overdue_logs=overdue_logs,
        expiring_warranties=expiring_warranties,
        high_risk=high_risk,
        recent_activity=recent_activity,
        recent_assets=recent_assets,
        today=today,
    )
