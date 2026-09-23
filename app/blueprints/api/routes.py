"""
API Blueprint — JSON endpoints for charts, global search, and notifications.
"""
from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date, timedelta
from app.blueprints.api import api_bp
from app.models import Asset, Department, MaintenanceLog, ActivityLog, User
from app.extensions import db


@api_bp.route("/search")
@login_required
def global_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})

    results = []

    # Assets
    asset_q = Asset.query.filter(
        db.or_(
            Asset.name.ilike(f"%{q}%"),
            Asset.asset_tag.ilike(f"%{q}%"),
            Asset.location.ilike(f"%{q}%"),
        )
    )
    if not current_user.is_admin:
        asset_q = asset_q.filter_by(department_id=current_user.department_id)
    for a in asset_q.limit(5).all():
        results.append({
            "type": "asset",
            "id": a.id,
            "title": a.name,
            "subtitle": f"{a.asset_tag} · {a.department.name if a.department else ''}",
            "url": f"/assets/{a.id}",
            "status": a.status,
        })

    # Maintenance
    maint_q = MaintenanceLog.query.join(Asset).filter(
        db.or_(
            MaintenanceLog.issue_description.ilike(f"%{q}%"),
            Asset.asset_tag.ilike(f"%{q}%"),
        )
    )
    for m in maint_q.limit(3).all():
        results.append({
            "type": "maintenance",
            "id": m.id,
            "title": f"Maintenance #{m.id}",
            "subtitle": (m.issue_description or "")[:60],
            "url": f"/maintenance/{m.id}",
            "status": m.status,
        })

    return jsonify({"results": results})


@api_bp.route("/charts/department-breakdown")
@login_required
def dept_breakdown():
    data = (
        db.session.query(Department.name, func.count(Asset.id))
        .outerjoin(Asset, Asset.department_id == Department.id)
        .group_by(Department.id, Department.name)
        .all()
    )
    return jsonify({
        "labels": [d[0] for d in data],
        "values": [d[1] for d in data],
    })


@api_bp.route("/charts/status-breakdown")
@login_required
def status_breakdown():
    data = (
        db.session.query(Asset.status, func.count(Asset.id))
        .group_by(Asset.status)
        .all()
    )
    return jsonify({
        "labels": [d[0].replace("_", " ").title() for d in data],
        "values": [d[1] for d in data],
    })


@api_bp.route("/charts/maintenance-trend")
@login_required
def maintenance_trend():
    """Last 6 months maintenance counts."""
    today = date.today()
    months = []
    counts = []
    for i in range(5, -1, -1):
        month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        count = MaintenanceLog.query.filter(
            MaintenanceLog.request_date >= month_start,
            MaintenanceLog.request_date < month_end,
        ).count()
        months.append(month_start.strftime("%b %Y"))
        counts.append(count)
    return jsonify({"labels": months, "values": counts})


@api_bp.route("/notifications")
@login_required
def notifications():
    today = date.today()
    thirty_days = today + timedelta(days=30)
    items = []

    overdue = MaintenanceLog.query.filter(
        MaintenanceLog.status.in_(["pending", "in_progress"]),
        MaintenanceLog.scheduled_date < today,
    ).limit(5).all()
    for m in overdue:
        items.append({
            "type": "overdue",
            "message": f"Overdue maintenance: {m.asset.asset_tag if m.asset else 'N/A'}",
            "url": f"/maintenance/{m.id}",
        })

    expiring = Asset.query.filter(
        Asset.warranty_expiry.isnot(None),
        Asset.warranty_expiry.between(today, thirty_days),
    ).limit(5).all()
    for a in expiring:
        days = (a.warranty_expiry - today).days
        items.append({
            "type": "warranty",
            "message": f"Warranty expires in {days}d: {a.asset_tag}",
            "url": f"/assets/{a.id}",
        })

    return jsonify({"count": len(items), "items": items})
