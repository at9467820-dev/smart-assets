"""
Maintenance Blueprint — Request workflow, status updates, cost logging.
"""
from datetime import date, datetime, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.blueprints.maintenance import maintenance_bp
from app.extensions import db
from app.models import MaintenanceLog, Asset, User, Department
from app.utils.decorators import log_activity
from app.utils.email_utils import send_maintenance_resolved_notification


@maintenance_bp.route("/")
@login_required
def list_logs():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    priority_filter = request.args.get("priority", "")
    dept_filter = request.args.get("department", "")

    query = MaintenanceLog.query.join(Asset)

    if current_user.is_department:
        query = query.filter(Asset.department_id == current_user.department_id)
    elif current_user.is_maintenance:
        query = query.filter(
            db.or_(
                MaintenanceLog.assigned_to_id == current_user.id,
                MaintenanceLog.status == "pending",
            )
        )

    if status_filter:
        query = query.filter(MaintenanceLog.status == status_filter)
    if priority_filter:
        query = query.filter(MaintenanceLog.priority == priority_filter)
    if dept_filter and current_user.is_admin:
        query = query.filter(Asset.department_id == dept_filter)

    logs = query.order_by(MaintenanceLog.created_at.desc()).paginate(page=page, per_page=20)
    departments = Department.query.order_by(Department.name).all()

    return render_template("maintenance/list.html", logs=logs, departments=departments,
                           status_filter=status_filter, priority_filter=priority_filter, dept_filter=dept_filter)


@maintenance_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    asset_id = request.args.get("asset_id", type=int)
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        asset_id = request.form.get("asset_id", type=int)
        asset = Asset.query.get_or_404(asset_id)

        if current_user.is_department and asset.department_id != current_user.department_id:
            flash("You can only request maintenance for your department's assets.", "danger")
            return redirect(url_for("maintenance.list_logs"))

        sched_str = request.form.get("scheduled_date")

        log = MaintenanceLog(
            asset_id=asset_id,
            requested_by_id=current_user.id,
            issue_description=request.form.get("issue_description", "").strip(),
            priority=request.form.get("priority", "medium"),
            scheduled_date=datetime.strptime(sched_str, "%Y-%m-%d").date() if sched_str else None,
            estimated_cost=float(request.form.get("estimated_cost") or 0),
            status="pending",
        )
        db.session.add(log)

        # Update asset status
        asset.status = "under_repair"
        db.session.commit()
        log_activity("CREATE", "MaintenanceLog", log.id, f"Maintenance requested for {asset.asset_tag}")
        flash("Maintenance request submitted.", "success")
        return redirect(url_for("maintenance.detail", log_id=log.id))

    # Preload assets for dropdown
    if current_user.is_admin or current_user.is_maintenance:
        assets = Asset.query.filter(Asset.status != "retired").order_by(Asset.asset_tag).all()
    else:
        assets = Asset.query.filter(
            Asset.department_id == current_user.department_id,
            Asset.status != "retired",
        ).order_by(Asset.asset_tag).all()

    selected_asset = Asset.query.get(asset_id) if asset_id else None
    return render_template("maintenance/form.html", assets=assets, selected_asset=selected_asset)


@maintenance_bp.route("/<int:log_id>")
@login_required
def detail(log_id):
    log = MaintenanceLog.query.get_or_404(log_id)
    maintenance_users = User.query.filter_by(role="maintenance", is_active=True).all()
    return render_template("maintenance/detail.html", log=log, maintenance_users=maintenance_users)


@maintenance_bp.route("/<int:log_id>/update", methods=["POST"])
@login_required
def update_status(log_id):
    log = MaintenanceLog.query.get_or_404(log_id)

    # Dept staff can only cancel their own requests
    if current_user.is_department:
        if log.requested_by_id != current_user.id:
            flash("Permission denied.", "danger")
            return redirect(url_for("maintenance.detail", log_id=log_id))
        new_status = request.form.get("status")
        if new_status not in ("cancelled",):
            flash("Department users can only cancel requests.", "danger")
            return redirect(url_for("maintenance.detail", log_id=log_id))
        log.status = new_status
        db.session.commit()
        flash("Request cancelled.", "info")
        return redirect(url_for("maintenance.list_logs"))

    new_status = request.form.get("status", log.status)
    assigned_id = request.form.get("assigned_to_id") or None
    completed_str = request.form.get("completed_date")
    next_due_str = request.form.get("next_due_date")

    log.status = new_status
    log.assigned_to_id = assigned_id
    log.technician_notes = request.form.get("technician_notes", "").strip()
    log.actual_cost = float(request.form.get("actual_cost") or log.actual_cost)
    log.completed_date = datetime.strptime(completed_str, "%Y-%m-%d").date() if completed_str else log.completed_date
    log.next_due_date = datetime.strptime(next_due_str, "%Y-%m-%d").date() if next_due_str else log.next_due_date

    # Update asset status accordingly
    if log.asset:
        if new_status == "resolved":
            log.asset.status = "active"
            # Email requester
            if log.requested_by and log.requested_by.email:
                try:
                    send_maintenance_resolved_notification(log, log.requested_by.email)
                except Exception:
                    pass
        elif new_status in ("pending", "in_progress"):
            log.asset.status = "under_repair"
        elif new_status == "cancelled":
            log.asset.status = "active"

    db.session.commit()
    log_activity("UPDATE", "MaintenanceLog", log.id, f"Maintenance {log.id} → {new_status}")
    flash(f"Maintenance status updated to '{new_status.replace('_', ' ').title()}'.", "success")
    return redirect(url_for("maintenance.detail", log_id=log_id))


@maintenance_bp.route("/<int:log_id>/delete", methods=["POST"])
@login_required
def delete(log_id):
    if not current_user.is_admin:
        flash("Only admins can delete maintenance records.", "danger")
        return redirect(url_for("maintenance.detail", log_id=log_id))
    log = MaintenanceLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    log_activity("DELETE", "MaintenanceLog", log_id, "Maintenance record deleted")
    flash("Maintenance record deleted.", "success")
    return redirect(url_for("maintenance.list_logs"))
