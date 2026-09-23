"""
Analysis Blueprint — Utilization analysis (underutilized + frequently damaged assets).
"""
from datetime import date, timedelta
from flask import render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app.blueprints.analysis import analysis_bp
from app.models import Asset, MaintenanceLog, Department
from app.extensions import db
from app.utils.cost_estimator import compute_risk_score, risk_label, risk_badge_class


@analysis_bp.route("/")
@login_required
def index():
    today = date.today()
    six_months_ago = today - timedelta(days=180)
    one_year_ago = today - timedelta(days=365)

    base_query = Asset.query
    if current_user.is_department:
        base_query = base_query.filter_by(department_id=current_user.department_id)

    # ── Underutilized: active, no maintenance logs in 6+ months, no allocation change ──
    all_active = base_query.filter_by(status="active").all()
    underutilized = []
    for a in all_active:
        last_activity = a.maintenance_logs.order_by(MaintenanceLog.created_at.desc()).first()
        if last_activity is None:
            idle_days = (today - a.purchase_date).days if a.purchase_date else 9999
        else:
            idle_days = (today - last_activity.request_date).days if last_activity.request_date else 9999
        if idle_days >= 180:
            underutilized.append({"asset": a, "idle_days": idle_days})
    underutilized.sort(key=lambda x: x["idle_days"], reverse=True)

    # ── Frequently damaged: 3+ maintenance logs in past year ──
    repair_counts = (
        db.session.query(Asset.id, func.count(MaintenanceLog.id).label("cnt"))
        .join(MaintenanceLog, MaintenanceLog.asset_id == Asset.id)
        .filter(MaintenanceLog.request_date >= one_year_ago)
        .group_by(Asset.id)
        .having(func.count(MaintenanceLog.id) >= 3)
        .all()
    )
    freq_damaged_ids = {r[0]: r[1] for r in repair_counts}
    frequently_damaged = []
    for a in base_query.filter(Asset.id.in_(freq_damaged_ids.keys())).all():
        frequently_damaged.append({"asset": a, "repairs_this_year": freq_damaged_ids[a.id]})
    frequently_damaged.sort(key=lambda x: x["repairs_this_year"], reverse=True)

    # ── High-risk assets ──────────────────────────────────────
    all_assets = base_query.filter(Asset.status != "retired").all()
    risk_assets = []
    for a in all_assets:
        score = compute_risk_score(a)
        if score >= 50:
            risk_assets.append({
                "asset": a,
                "score": score,
                "label": risk_label(score),
                "badge": risk_badge_class(score),
            })
    risk_assets.sort(key=lambda x: x["score"], reverse=True)

    # ── Department utilization stats ──────────────────────────
    departments = Department.query.order_by(Department.name).all()
    dept_stats = []
    for d in departments:
        total = d.assets.count()
        active = d.assets.filter_by(status="active").count()
        under_rep = d.assets.filter_by(status="under_repair").count()
        damaged = d.assets.filter_by(status="damaged").count()
        retired = d.assets.filter_by(status="retired").count()
        dept_stats.append({
            "dept": d,
            "total": total,
            "active": active,
            "under_repair": under_rep,
            "damaged": damaged,
            "retired": retired,
            "utilization_pct": round(active / total * 100, 1) if total > 0 else 0,
        })

    return render_template(
        "analysis/index.html",
        underutilized=underutilized,
        frequently_damaged=frequently_damaged,
        risk_assets=risk_assets,
        dept_stats=dept_stats,
    )
