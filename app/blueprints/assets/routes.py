"""
Assets Blueprint — Full CRUD, QR, photo upload, CSV import, scanner.
"""
import os
import csv
import io
from datetime import date, datetime
from flask import (
    render_template, redirect, url_for, flash, request,
    current_app, send_from_directory, jsonify, make_response
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.blueprints.assets import assets_bp
from app.extensions import db
from app.models import Asset, Department, User, AllocationHistory
from app.utils.decorators import log_activity
from app.utils.qr_generator import generate_asset_qr
from app.utils.cost_estimator import (
    current_book_value, estimated_maintenance_cost,
    estimated_replacement_cost, compute_risk_score, risk_label, risk_badge_class
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _generate_asset_tag(dept_code: str) -> str:
    """Auto-generate asset tag like CSE-042."""
    from sqlalchemy import func
    count = db.session.query(func.count(Asset.id)).scalar() or 0
    return f"{dept_code.upper()}-{count + 1:03d}"


def _get_base_url():
    return request.host_url.rstrip("/")


# ─────────────────────────────────────────────────────────────
# List & Search
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/")
@login_required
def list_assets():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    q = request.args.get("q", "").strip()
    dept_filter = request.args.get("department", "")
    status_filter = request.args.get("status", "")
    category_filter = request.args.get("category", "")

    query = Asset.query

    # Role-based filter
    if not current_user.is_admin and current_user.role != "maintenance":
        query = query.filter_by(department_id=current_user.department_id)

    if q:
        query = query.filter(
            db.or_(
                Asset.name.ilike(f"%{q}%"),
                Asset.asset_tag.ilike(f"%{q}%"),
                Asset.location.ilike(f"%{q}%"),
                Asset.serial_number.ilike(f"%{q}%"),
            )
        )
    if dept_filter:
        query = query.filter(Asset.department_id == dept_filter)
    if status_filter:
        query = query.filter(Asset.status == status_filter)
    if category_filter:
        query = query.filter(Asset.category == category_filter)

    assets = query.order_by(Asset.created_at.desc()).paginate(page=page, per_page=per_page)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "assets/list.html",
        assets=assets, departments=departments,
        q=q, dept_filter=dept_filter,
        status_filter=status_filter, category_filter=category_filter,
    )


# ─────────────────────────────────────────────────────────────
# Detail
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/<int:asset_id>")
@login_required
def detail(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    # Dept staff can only view their own department's assets
    if current_user.is_department and asset.department_id != current_user.department_id:
        flash("You don't have permission to view this asset.", "danger")
        return redirect(url_for("assets.list_assets"))

    maintenance_history = (
        asset.maintenance_logs
        .order_by(db.desc("created_at"))
        .limit(10)
        .all()
    )
    allocation_history = (
        asset.allocation_history
        .order_by(db.desc("created_at"))
        .all()
    )
    timeline = _build_timeline(asset, maintenance_history, allocation_history)

    risk = compute_risk_score(asset)
    maint_cost = estimated_maintenance_cost(asset)
    repl_cost = estimated_replacement_cost(asset)
    book_val = current_book_value(asset)

    return render_template(
        "assets/detail.html",
        asset=asset,
        maintenance_history=maintenance_history,
        allocation_history=allocation_history,
        timeline=timeline,
        risk_score=risk,
        risk_label=risk_label(risk),
        risk_badge=risk_badge_class(risk),
        maint_cost=maint_cost,
        repl_cost=repl_cost,
        book_val=book_val,
    )


def _build_timeline(asset, maintenance_logs, allocation_history):
    """Build a unified timeline list for the asset lifecycle view."""
    events = []
    if asset.purchase_date:
        events.append({
            "date": asset.purchase_date,
            "type": "purchase",
            "icon": "bi-bag-check",
            "color": "success",
            "title": "Asset Acquired",
            "desc": f"Purchased for ₹{float(asset.purchase_cost or 0):,.0f}",
        })
    for alloc in allocation_history:
        events.append({
            "date": alloc.allocation_date,
            "type": "allocation",
            "icon": "bi-arrow-left-right",
            "color": "info",
            "title": "Reallocated",
            "desc": f"Moved to {alloc.to_department.name if alloc.to_department else 'N/A'}",
        })
    for log in maintenance_logs:
        events.append({
            "date": log.request_date,
            "type": "maintenance",
            "icon": "bi-tools",
            "color": "warning",
            "title": f"Maintenance ({log.status.replace('_', ' ').title()})",
            "desc": (log.issue_description or "")[:60],
        })
    events.sort(key=lambda e: e["date"] or date.min, reverse=True)
    return events


# ─────────────────────────────────────────────────────────────
# Create
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if current_user.is_maintenance:
        flash("Maintenance staff cannot create assets.", "danger")
        return redirect(url_for("assets.list_assets"))

    departments = Department.query.order_by(Department.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == "POST":
        dept_id = request.form.get("department_id")
        dept = Department.query.get(dept_id)
        if not dept:
            flash("Invalid department.", "danger")
            return render_template("assets/form.html", departments=departments, users=users, asset=None)

        # Role check: dept staff can only add to their department
        if current_user.is_department and str(current_user.department_id) != str(dept_id):
            flash("You can only add assets to your own department.", "danger")
            return render_template("assets/form.html", departments=departments, users=users, asset=None)

        purchase_date_str = request.form.get("purchase_date")
        warranty_str = request.form.get("warranty_expiry")

        asset = Asset(
            asset_tag=request.form.get("asset_tag") or _generate_asset_tag(dept.code),
            name=request.form.get("name", "").strip(),
            category=request.form.get("category", "Other"),
            department_id=dept_id,
            location=request.form.get("location", "").strip(),
            purchase_date=datetime.strptime(purchase_date_str, "%Y-%m-%d").date() if purchase_date_str else None,
            purchase_cost=float(request.form.get("purchase_cost") or 0),
            warranty_expiry=datetime.strptime(warranty_str, "%Y-%m-%d").date() if warranty_str else None,
            status=request.form.get("status", "active"),
            condition_rating=int(request.form.get("condition_rating") or 5),
            assigned_to_id=request.form.get("assigned_to_id") or None,
            serial_number=request.form.get("serial_number", "").strip(),
            model_number=request.form.get("model_number", "").strip(),
            manufacturer=request.form.get("manufacturer", "").strip(),
            notes=request.form.get("notes", "").strip(),
        )

        # Handle photo upload
        photo = request.files.get("photo")
        if photo and photo.filename and _allowed_file(photo.filename):
            fn = secure_filename(f"asset_{asset.asset_tag}_{photo.filename}")
            photo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fn))
            asset.photo_path = f"uploads/{fn}"

        db.session.add(asset)
        db.session.flush()  # get ID

        # Generate QR code
        try:
            qr_path = generate_asset_qr(asset, _get_base_url())
            asset.qr_code_path = qr_path
        except Exception as e:
            current_app.logger.warning(f"QR generation failed: {e}")

        db.session.commit()
        log_activity("CREATE", "Asset", asset.id, f"Created asset {asset.asset_tag}")
        flash(f"Asset '{asset.name}' ({asset.asset_tag}) created successfully.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.id))

    return render_template("assets/form.html", departments=departments, users=users, asset=None)


# ─────────────────────────────────────────────────────────────
# Edit
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/<int:asset_id>/edit", methods=["GET", "POST"])
@login_required
def edit(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    if current_user.is_maintenance:
        flash("Maintenance staff cannot edit asset details.", "danger")
        return redirect(url_for("assets.detail", asset_id=asset_id))
    if current_user.is_department and asset.department_id != current_user.department_id:
        flash("Access denied.", "danger")
        return redirect(url_for("assets.list_assets"))

    departments = Department.query.order_by(Department.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == "POST":
        purchase_date_str = request.form.get("purchase_date")
        warranty_str = request.form.get("warranty_expiry")
        old_dept = asset.department_id

        asset.name = request.form.get("name", asset.name).strip()
        asset.category = request.form.get("category", asset.category)
        asset.department_id = request.form.get("department_id", asset.department_id)
        asset.location = request.form.get("location", "").strip()
        asset.purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d").date() if purchase_date_str else asset.purchase_date
        asset.purchase_cost = float(request.form.get("purchase_cost") or asset.purchase_cost)
        asset.warranty_expiry = datetime.strptime(warranty_str, "%Y-%m-%d").date() if warranty_str else asset.warranty_expiry
        asset.status = request.form.get("status", asset.status)
        asset.condition_rating = int(request.form.get("condition_rating") or asset.condition_rating)
        asset.assigned_to_id = request.form.get("assigned_to_id") or None
        asset.serial_number = request.form.get("serial_number", "").strip()
        asset.model_number = request.form.get("model_number", "").strip()
        asset.manufacturer = request.form.get("manufacturer", "").strip()
        asset.notes = request.form.get("notes", "").strip()

        # Photo update
        photo = request.files.get("photo")
        if photo and photo.filename and _allowed_file(photo.filename):
            fn = secure_filename(f"asset_{asset.asset_tag}_{photo.filename}")
            photo.save(os.path.join(current_app.config["UPLOAD_FOLDER"], fn))
            asset.photo_path = f"uploads/{fn}"

        # Log reallocation
        if str(old_dept) != str(asset.department_id):
            alloc = AllocationHistory(
                asset_id=asset.id,
                from_department_id=old_dept,
                to_department_id=asset.department_id,
                allocated_by_id=current_user.id,
                reason="Department transfer via edit",
            )
            db.session.add(alloc)

        db.session.commit()
        log_activity("UPDATE", "Asset", asset.id, f"Updated asset {asset.asset_tag}")
        flash("Asset updated successfully.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.id))

    return render_template("assets/form.html", departments=departments, users=users, asset=asset)


# ─────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/<int:asset_id>/delete", methods=["POST"])
@login_required
def delete(asset_id):
    if not current_user.is_admin:
        flash("Only administrators can delete assets.", "danger")
        return redirect(url_for("assets.detail", asset_id=asset_id))
    asset = Asset.query.get_or_404(asset_id)
    tag = asset.asset_tag
    db.session.delete(asset)
    db.session.commit()
    log_activity("DELETE", "Asset", asset_id, f"Deleted asset {tag}")
    flash(f"Asset {tag} deleted.", "success")
    return redirect(url_for("assets.list_assets"))


# ─────────────────────────────────────────────────────────────
# QR Scanner page
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/scanner")
@login_required
def scanner():
    return render_template("assets/scanner.html")


# ─────────────────────────────────────────────────────────────
# QR Regenerate
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/<int:asset_id>/regenerate-qr", methods=["POST"])
@login_required
def regenerate_qr(asset_id):
    if not current_user.is_admin:
        flash("Only admins can regenerate QR codes.", "danger")
        return redirect(url_for("assets.detail", asset_id=asset_id))
    asset = Asset.query.get_or_404(asset_id)
    try:
        qr_path = generate_asset_qr(asset, _get_base_url())
        asset.qr_code_path = qr_path
        db.session.commit()
        flash("QR code regenerated.", "success")
    except Exception as e:
        flash(f"QR generation failed: {e}", "danger")
    return redirect(url_for("assets.detail", asset_id=asset_id))


# ─────────────────────────────────────────────────────────────
# CSV Bulk Import
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/import-csv", methods=["GET", "POST"])
@login_required
def import_csv():
    if not current_user.is_admin:
        flash("Only administrators can bulk import assets.", "danger")
        return redirect(url_for("assets.list_assets"))

    departments = Department.query.order_by(Department.name).all()
    dept_map = {d.code.upper(): d.id for d in departments}

    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or not f.filename.endswith(".csv"):
            flash("Please upload a valid CSV file.", "danger")
            return render_template("assets/import_csv.html")

        stream = io.StringIO(f.stream.read().decode("utf-8"))
        reader = csv.DictReader(stream)
        created = 0
        errors = []

        for i, row in enumerate(reader, 1):
            try:
                dept_code = row.get("department_code", "").strip().upper()
                dept_id = dept_map.get(dept_code)
                if not dept_id:
                    errors.append(f"Row {i}: Unknown department '{dept_code}'")
                    continue
                dept = Department.query.get(dept_id)

                pd_str = row.get("purchase_date", "").strip()
                we_str = row.get("warranty_expiry", "").strip()

                asset = Asset(
                    asset_tag=row.get("asset_tag", "").strip() or _generate_asset_tag(dept.code),
                    name=row.get("name", "").strip(),
                    category=row.get("category", "Other").strip(),
                    department_id=dept_id,
                    location=row.get("location", "").strip(),
                    purchase_date=datetime.strptime(pd_str, "%Y-%m-%d").date() if pd_str else None,
                    purchase_cost=float(row.get("purchase_cost") or 0),
                    warranty_expiry=datetime.strptime(we_str, "%Y-%m-%d").date() if we_str else None,
                    status=row.get("status", "active"),
                    serial_number=row.get("serial_number", "").strip(),
                    manufacturer=row.get("manufacturer", "").strip(),
                    notes=row.get("notes", "").strip(),
                )
                db.session.add(asset)
                db.session.flush()
                try:
                    qr_path = generate_asset_qr(asset, _get_base_url())
                    asset.qr_code_path = qr_path
                except Exception:
                    pass
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        db.session.commit()
        log_activity("IMPORT", "Asset", None, f"CSV import: {created} assets created")
        flash(f"Import complete. {created} assets created.", "success")
        if errors:
            for err in errors[:5]:
                flash(err, "warning")
        return redirect(url_for("assets.list_assets"))

    return render_template("assets/import_csv.html")


# ─────────────────────────────────────────────────────────────
# Allocation
# ─────────────────────────────────────────────────────────────
@assets_bp.route("/<int:asset_id>/allocate", methods=["GET", "POST"])
@login_required
def allocate(asset_id):
    if not current_user.is_admin:
        flash("Only administrators can reallocate assets.", "danger")
        return redirect(url_for("assets.detail", asset_id=asset_id))
    asset = Asset.query.get_or_404(asset_id)
    departments = Department.query.order_by(Department.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.full_name).all()

    if request.method == "POST":
        new_dept_id = request.form.get("to_department_id")
        new_user_id = request.form.get("to_user_id") or None
        reason = request.form.get("reason", "").strip()

        alloc = AllocationHistory(
            asset_id=asset.id,
            from_department_id=asset.department_id,
            to_department_id=new_dept_id,
            from_user_id=asset.assigned_to_id,
            to_user_id=new_user_id,
            allocated_by_id=current_user.id,
            reason=reason,
        )
        db.session.add(alloc)
        asset.department_id = new_dept_id
        asset.assigned_to_id = new_user_id
        db.session.commit()
        log_activity("ALLOCATE", "Asset", asset.id, f"Asset {asset.asset_tag} reallocated")
        flash("Asset reallocated successfully.", "success")
        return redirect(url_for("assets.detail", asset_id=asset.id))

    return render_template("assets/allocate.html", asset=asset, departments=departments, users=users)
