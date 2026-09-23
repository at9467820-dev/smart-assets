"""
Budget Blueprint — Cost estimation, annual budget summary, budget vs actual chart.
"""
from datetime import date
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, extract
from app.blueprints.budget import budget_bp
from app.extensions import db
from app.models import Asset, Department, BudgetEstimate, MaintenanceLog
from app.utils.decorators import admin_required, log_activity
from app.utils.cost_estimator import (
    estimated_maintenance_cost, estimated_replacement_cost, current_book_value
)


@budget_bp.route("/")
@login_required
def index():
    current_year = date.today().year
    departments = Department.query.order_by(Department.name).all()

    # Auto-compute budget estimates from current asset data
    dept_summaries = []
    for dept in departments:
        assets = dept.assets.filter(Asset.status != "retired").all()
        total_maint = sum(estimated_maintenance_cost(a) for a in assets)
        total_repl = sum(estimated_replacement_cost(a) for a in assets)

        # Actual spent (from resolved maintenance logs this year)
        actual = (
            db.session.query(func.sum(MaintenanceLog.actual_cost))
            .join(Asset)
            .filter(
                Asset.department_id == dept.id,
                MaintenanceLog.status == "resolved",
                extract("year", MaintenanceLog.completed_date) == current_year,
            )
            .scalar() or 0
        )
        dept_summaries.append({
            "dept": dept,
            "asset_count": len(assets),
            "estimated_maintenance": total_maint,
            "estimated_replacement": total_repl,
            "total_estimated": total_maint + total_repl,
            "actual_spent": float(actual),
            "variance": float(actual) - (total_maint + total_repl),
        })

    # Saved estimates for this year
    saved_estimates = (
        BudgetEstimate.query
        .filter_by(fiscal_year=current_year)
        .order_by(BudgetEstimate.department_id)
        .all()
    )

    # Chart data: estimated vs actual by department
    chart_labels = [s["dept"].name for s in dept_summaries]
    chart_estimated = [round(s["total_estimated"], 2) for s in dept_summaries]
    chart_actual = [round(s["actual_spent"], 2) for s in dept_summaries]

    grand_total_estimated = sum(s["total_estimated"] for s in dept_summaries)
    grand_total_actual = sum(s["actual_spent"] for s in dept_summaries)

    return render_template(
        "budget/index.html",
        current_year=current_year,
        dept_summaries=dept_summaries,
        saved_estimates=saved_estimates,
        chart_labels=chart_labels,
        chart_estimated=chart_estimated,
        chart_actual=chart_actual,
        grand_total_estimated=grand_total_estimated,
        grand_total_actual=grand_total_actual,
    )


@budget_bp.route("/save", methods=["POST"])
@login_required
@admin_required
def save_estimates():
    current_year = date.today().year
    departments = Department.query.all()

    # Delete old estimates for this year
    BudgetEstimate.query.filter_by(fiscal_year=current_year).delete()

    for dept in departments:
        assets = dept.assets.filter(Asset.status != "retired").all()
        total_maint = sum(estimated_maintenance_cost(a) for a in assets)
        total_repl = sum(estimated_replacement_cost(a) for a in assets)

        actual = (
            db.session.query(func.sum(MaintenanceLog.actual_cost))
            .join(Asset)
            .filter(
                Asset.department_id == dept.id,
                MaintenanceLog.status == "resolved",
                extract("year", MaintenanceLog.completed_date) == current_year,
            )
            .scalar() or 0
        )

        est = BudgetEstimate(
            department_id=dept.id,
            fiscal_year=current_year,
            category="All",
            estimated_maintenance_cost=total_maint,
            estimated_replacement_cost=total_repl,
            actual_spent=actual,
            prepared_by_id=current_user.id,
        )
        db.session.add(est)

    db.session.commit()
    log_activity("GENERATE", "BudgetEstimate", None, f"Budget FY{current_year} saved")
    flash(f"Budget estimates for FY{current_year} saved.", "success")
    return redirect(url_for("budget.index"))


@budget_bp.route("/asset/<int:asset_id>")
@login_required
def asset_cost_detail(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    return render_template(
        "budget/asset_detail.html",
        asset=asset,
        book_value=current_book_value(asset),
        maint_cost=estimated_maintenance_cost(asset),
        repl_cost=estimated_replacement_cost(asset),
    )
