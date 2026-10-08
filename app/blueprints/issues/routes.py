"""
AssetPulse — Material & Asset Issue Blueprint
Handles issuing assets, generating Gate Passes / Parchi (PDF & Print), tracking returns,
and live scanner quick actions.
"""
from datetime import datetime, date, timedelta
from flask import (
    render_template, redirect, url_for, flash, request,
    send_file, jsonify, current_app
)
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app.blueprints.issues import issues_bp
from app.extensions import db
from app.models import AssetIssue, Asset, Department, User
from app.utils.decorators import log_activity
from app.utils.parchi_generator import generate_issue_parchi_pdf, generate_return_parchi_pdf


def _generate_slip_number() -> str:
    """Generate sequential slip number like GP-2026-0001."""
    year = datetime.utcnow().year
    count = db.session.query(func.count(AssetIssue.id)).scalar() or 0
    return f"GP-{year}-{count + 1:04d}"


def _get_base_url():
    return request.host_url.rstrip("/")


# ─────────────────────────────────────────────────────────────
# 1. List & Track Material Issues
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/")
@login_required
def list_issues():
    tab = request.args.get("tab", "active")
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    dept_id = request.args.get("department")

    now = datetime.utcnow()
    query = AssetIssue.query.join(Asset)

    # Department filter for non-admin/non-maint staff
    if current_user.is_department:
        query = query.filter(Asset.department_id == current_user.department_id)
    elif dept_id:
        query = query.filter(Asset.department_id == dept_id)

    # Filter tab
    if tab == "active":
        query = query.filter(AssetIssue.status == "issued")
    elif tab == "overdue":
        query = query.filter(
            AssetIssue.status == "issued",
            AssetIssue.expected_return_date.isnot(None),
            AssetIssue.expected_return_date < now
        )
    elif tab == "returned":
        query = query.filter(AssetIssue.status.in_(["returned", "damaged_returned"]))
    elif tab == "today":
        today_start = datetime.combine(date.today(), datetime.min.time())
        query = query.filter(AssetIssue.issue_date >= today_start)

    # Search keyword
    if q:
        query = query.filter(
            or_(
                AssetIssue.slip_number.ilike(f"%{q}%"),
                AssetIssue.issued_to_name.ilike(f"%{q}%"),
                AssetIssue.issued_to_id_number.ilike(f"%{q}%"),
                AssetIssue.purpose.ilike(f"%{q}%"),
                Asset.name.ilike(f"%{q}%"),
                Asset.asset_tag.ilike(f"%{q}%"),
            )
        )

    # KPIs / Summary counts
    base_q = AssetIssue.query.join(Asset)
    if current_user.is_department:
        base_q = base_q.filter(Asset.department_id == current_user.department_id)

    total_count = base_q.count()
    active_count = base_q.filter(AssetIssue.status == "issued").count()
    overdue_count = base_q.filter(
        AssetIssue.status == "issued",
        AssetIssue.expected_return_date.isnot(None),
        AssetIssue.expected_return_date < now
    ).count()
    returned_count = base_q.filter(AssetIssue.status.in_(["returned", "damaged_returned"])).count()

    issues_paged = query.order_by(AssetIssue.issue_date.desc()).paginate(page=page, per_page=20)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "issues/list.html",
        issues=issues_paged,
        tab=tab,
        q=q,
        dept_id=dept_id,
        departments=departments,
        total_count=total_count,
        active_count=active_count,
        overdue_count=overdue_count,
        returned_count=returned_count,
    )


# ─────────────────────────────────────────────────────────────
# 2. Issue Material / Asset (Create Gate Pass)
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    asset_id = request.args.get("asset_id", type=int)
    preselected_asset = Asset.query.get(asset_id) if asset_id else None

    # Available assets for selection
    asset_query = Asset.query.filter(Asset.status.in_(["active", "under_repair"]))
    if current_user.is_department:
        asset_query = asset_query.filter(Asset.department_id == current_user.department_id)
    available_assets = asset_query.order_by(Asset.asset_tag).all()

    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        target_asset_id = request.form.get("asset_id", type=int)
        asset = Asset.query.get_or_404(target_asset_id)

        # Permission check
        if current_user.is_department and asset.department_id != current_user.department_id:
            flash("You can only issue assets belonging to your department.", "danger")
            return redirect(url_for("issues.create"))

        # Check if asset is already issued out
        if asset.is_currently_issued:
            curr_issue = asset.current_issue
            flash(f"Asset {asset.asset_tag} is already issued to {curr_issue.issued_to_name} (Slip: {curr_issue.slip_number}). Please return it first.", "warning")
            return redirect(url_for("issues.detail", issue_id=curr_issue.id))

        # Expected return date parsing
        return_dt_str = request.form.get("expected_return_date")
        expected_return_dt = None
        if return_dt_str:
            try:
                expected_return_dt = datetime.strptime(return_dt_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                try:
                    expected_return_dt = datetime.strptime(return_dt_str, "%Y-%m-%d")
                except ValueError:
                    pass

        slip_number = _generate_slip_number()
        issuer_name = current_user.full_name or current_user.username

        issue = AssetIssue(
            slip_number=slip_number,
            asset_id=asset.id,
            issued_by_id=current_user.id,
            issuer_name=issuer_name,
            issued_to_name=request.form.get("issued_to_name", "").strip(),
            issued_to_id_number=request.form.get("issued_to_id_number", "").strip(),
            issued_to_dept=request.form.get("issued_to_dept", "").strip(),
            issued_to_phone=request.form.get("issued_to_phone", "").strip(),
            issued_to_email=request.form.get("issued_to_email", "").strip(),
            purpose=request.form.get("purpose", "").strip(),
            gate_pass_type=request.form.get("gate_pass_type", "returnable"),
            issue_date=datetime.utcnow(),
            expected_return_date=expected_return_dt,
            issue_condition=request.form.get("issue_condition", "Good / Functional"),
            remarks_on_issue=request.form.get("remarks_on_issue", "").strip(),
            status="issued",
        )

        db.session.add(issue)
        db.session.commit()

        log_activity("ISSUE", "AssetIssue", issue.id, f"Issued asset {asset.asset_tag} to {issue.issued_to_name} (Slip #{slip_number})")
        flash(f"Gate Pass #{slip_number} created successfully! Material issued to {issue.issued_to_name}.", "success")
        return redirect(url_for("issues.detail", issue_id=issue.id))

    return render_template(
        "issues/form.html",
        preselected_asset=preselected_asset,
        available_assets=available_assets,
        departments=departments,
    )


# ─────────────────────────────────────────────────────────────
# 3. View Issue Slip / Gate Pass (Parchi Detail View)
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/<int:issue_id>")
@login_required
def detail(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    return render_template("issues/detail.html", issue=issue)


# ─────────────────────────────────────────────────────────────
# 4. Printable HTML Parchi View (Auto-Print Gate Pass)
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/<int:issue_id>/print")
@login_required
def print_parchi(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    return render_template("issues/print_parchi.html", issue=issue)


# ─────────────────────────────────────────────────────────────
# 5. Download Official PDF Parchi
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/<int:issue_id>/pdf")
@login_required
def download_pdf(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    buf = generate_issue_parchi_pdf(issue, _get_base_url())
    return send_file(
        buf,
        download_name=f"GatePass_{issue.slip_number}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )


# ─────────────────────────────────────────────────────────────
# 6. Process Return (Check-In Asset)
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/<int:issue_id>/return", methods=["POST"])
@login_required
def return_asset(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)

    if issue.status != "issued":
        flash("This material issue is already closed/returned.", "info")
        return redirect(url_for("issues.detail", issue_id=issue.id))

    return_condition = request.form.get("return_condition", "Good / Functional")
    remarks_on_return = request.form.get("remarks_on_return", "").strip()
    fine_amount = float(request.form.get("fine_amount") or 0.0)

    issue.actual_return_date = datetime.utcnow()
    issue.received_by_id = current_user.id
    issue.return_condition = return_condition
    issue.remarks_on_return = remarks_on_return
    issue.fine_amount = fine_amount

    if "Damaged" in return_condition or "Faulty" in return_condition or "Broken" in return_condition:
        issue.status = "damaged_returned"
        issue.asset.status = "damaged"
    else:
        issue.status = "returned"
        # Reset asset status to active if it was not retired
        if issue.asset.status != "retired":
            issue.asset.status = "active"

    db.session.commit()
    log_activity("RETURN", "AssetIssue", issue.id, f"Asset {issue.asset.asset_tag} returned by {issue.issued_to_name} (Condition: {return_condition})")
    flash(f"Asset {issue.asset.asset_tag} successfully returned & verified! Return clearance slip generated.", "success")
    return redirect(url_for("issues.detail", issue_id=issue.id))


# ─────────────────────────────────────────────────────────────
# 7. Download Return Receipt PDF
# ─────────────────────────────────────────────────────────────
@issues_bp.route("/<int:issue_id>/return-pdf")
@login_required
def download_return_pdf(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    buf = generate_return_parchi_pdf(issue, _get_base_url())
    return send_file(
        buf,
        download_name=f"ReturnClearance_{issue.slip_number}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )
