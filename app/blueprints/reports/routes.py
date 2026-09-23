"""
Reports Blueprint — Inventory, Maintenance, Budget reports + PDF/Excel export + bulk QR sheet.
"""
from flask import render_template, request, send_file, flash, redirect, url_for, Response
from flask_login import login_required, current_user
from app.blueprints.reports import reports_bp
from app.models import Asset, MaintenanceLog, BudgetEstimate, Department
from app.utils.pdf_export import generate_inventory_pdf, generate_maintenance_pdf, generate_budget_pdf
from app.utils.excel_export import generate_inventory_excel, generate_maintenance_excel, generate_budget_excel
from app.utils.qr_generator import generate_bulk_qr_pdf
import io
import csv
from datetime import date


def _get_base_url():
    return request.host_url.rstrip("/")


def _filter_assets():
    q = Asset.query
    if not current_user.is_admin:
        q = q.filter_by(department_id=current_user.department_id)
    dept = request.args.get("department")
    status = request.args.get("status")
    category = request.args.get("category")
    if dept:
        q = q.filter(Asset.department_id == dept)
    if status:
        q = q.filter(Asset.status == status)
    if category:
        q = q.filter(Asset.category == category)
    return q.order_by(Asset.department_id, Asset.asset_tag).all()


def _filter_logs():
    q = MaintenanceLog.query.join(Asset)
    if not current_user.is_admin:
        q = q.filter(Asset.department_id == current_user.department_id)
    status = request.args.get("status")
    dept = request.args.get("department")
    if status:
        q = q.filter(MaintenanceLog.status == status)
    if dept:
        q = q.filter(Asset.department_id == dept)
    return q.order_by(MaintenanceLog.created_at.desc()).all()


@reports_bp.route("/")
@login_required
def index():
    departments = Department.query.order_by(Department.name).all()
    return render_template("reports/index.html", departments=departments)


# ── Inventory Report ──────────────────────────────────────────
@reports_bp.route("/inventory")
@login_required
def inventory():
    assets = _filter_assets()
    departments = Department.query.order_by(Department.name).all()
    fmt = request.args.get("format")

    if fmt == "pdf":
        buf = generate_inventory_pdf(assets)
        return send_file(buf, download_name=f"inventory_report_{date.today()}.pdf",
                         as_attachment=True, mimetype="application/pdf")
    if fmt == "excel":
        buf = generate_inventory_excel(assets)
        return send_file(buf, download_name=f"inventory_report_{date.today()}.xlsx",
                         as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "csv":
        return _inventory_csv(assets)

    return render_template("reports/inventory.html", assets=assets, departments=departments)


def _inventory_csv(assets):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Asset Tag", "Name", "Category", "Department", "Location",
                     "Status", "Purchase Date", "Cost", "Warranty Expiry", "Condition"])
    for a in assets:
        writer.writerow([
            a.asset_tag, a.name, a.category,
            a.department.name if a.department else "",
            a.location or "",
            a.status_label,
            a.purchase_date.strftime("%Y-%m-%d") if a.purchase_date else "",
            float(a.purchase_cost or 0),
            a.warranty_expiry.strftime("%Y-%m-%d") if a.warranty_expiry else "",
            a.condition_rating,
        ])
    output.seek(0)
    return Response(output, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=inventory_{date.today()}.csv"})


# ── Maintenance Report ────────────────────────────────────────
@reports_bp.route("/maintenance")
@login_required
def maintenance():
    logs = _filter_logs()
    departments = Department.query.order_by(Department.name).all()
    fmt = request.args.get("format")

    if fmt == "pdf":
        buf = generate_maintenance_pdf(logs)
        return send_file(buf, download_name=f"maintenance_report_{date.today()}.pdf",
                         as_attachment=True, mimetype="application/pdf")
    if fmt == "excel":
        buf = generate_maintenance_excel(logs)
        return send_file(buf, download_name=f"maintenance_report_{date.today()}.xlsx",
                         as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return render_template("reports/maintenance.html", logs=logs, departments=departments)


# ── Budget Report ─────────────────────────────────────────────
@reports_bp.route("/budget")
@login_required
def budget():
    current_year = date.today().year
    estimates = BudgetEstimate.query.filter_by(fiscal_year=current_year).all()
    departments = Department.query.all()
    fmt = request.args.get("format")

    if fmt == "pdf":
        buf = generate_budget_pdf(estimates, departments)
        return send_file(buf, download_name=f"budget_report_{current_year}.pdf",
                         as_attachment=True, mimetype="application/pdf")
    if fmt == "excel":
        buf = generate_budget_excel(estimates)
        return send_file(buf, download_name=f"budget_report_{current_year}.xlsx",
                         as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return render_template("reports/budget.html", estimates=estimates, current_year=current_year)


# ── Bulk QR Label Sheet ───────────────────────────────────────
@reports_bp.route("/qr-labels", methods=["GET", "POST"])
@login_required
def qr_labels():
    if not current_user.is_admin:
        flash("Only admins can generate QR label sheets.", "danger")
        return redirect(url_for("reports.index"))

    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        dept_ids = request.form.getlist("departments")
        if dept_ids:
            assets = Asset.query.filter(Asset.department_id.in_(dept_ids)).order_by(Asset.asset_tag).all()
        else:
            assets = Asset.query.order_by(Asset.asset_tag).all()

        base_url = _get_base_url()
        buf = generate_bulk_qr_pdf(assets, base_url)
        return send_file(buf, download_name=f"qr_labels_{date.today()}.pdf",
                         as_attachment=True, mimetype="application/pdf")

    return render_template("reports/qr_labels.html", departments=departments)
