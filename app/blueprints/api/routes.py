"""
AssetPulse — Comprehensive REST API Blueprint
Powers the modern React frontend with complete CRUD, QR scanning, stats, gate pass issue & return, and procurement.
"""
from flask import jsonify, request, current_app, send_file
from sqlalchemy import func, or_, desc
from datetime import date, datetime, timedelta
from app.blueprints.api import api_bp
from app.models import (
    Asset, Department, MaintenanceLog, ActivityLog, User,
    AssetIssue, AssetOrder, AllocationHistory, BudgetEstimate
)
from app.extensions import db
from app.utils.qr_generator import generate_asset_qr
from app.utils.parchi_generator import generate_issue_parchi_pdf
from app.utils.cost_estimator import (
    compute_risk_score, current_book_value, estimated_maintenance_cost,
    estimated_replacement_cost, risk_label
)


def _get_base_url():
    return request.host_url.rstrip("/")


def _generate_asset_tag(dept_code: str) -> str:
    count = db.session.query(func.count(Asset.id)).scalar() or 0
    return f"{dept_code.upper()}-{count + 1:03d}"


def _generate_slip_number() -> str:
    year = datetime.utcnow().year
    count = db.session.query(func.count(AssetIssue.id)).scalar() or 0
    return f"GP-{year}-{count + 1:04d}"


def _generate_order_number() -> str:
    year = date.today().year
    count = db.session.query(func.count(AssetOrder.id)).scalar() or 0
    return f"ORD-{year}-{count + 1:04d}"


# ─────────────────────────────────────────────────────────────
# 1. Dashboard Overview Stats & KPIs
# ─────────────────────────────────────────────────────────────
@api_bp.route("/dashboard/stats")
def dashboard_stats():
    total_assets = Asset.query.count()
    active_assets = Asset.query.filter_by(status="active").count()
    repair_assets = Asset.query.filter_by(status="under_repair").count()
    damaged_assets = Asset.query.filter_by(status="damaged").count()
    retired_assets = Asset.query.filter_by(status="retired").count()

    # Issues / Gate Passes
    now = datetime.utcnow()
    total_issues = AssetIssue.query.count()
    active_issues = AssetIssue.query.filter_by(status="issued").count()
    overdue_issues = AssetIssue.query.filter(
        AssetIssue.status == "issued",
        AssetIssue.expected_return_date.isnot(None),
        AssetIssue.expected_return_date < now,
    ).count()
    returned_issues = AssetIssue.query.filter(AssetIssue.status.in_(["returned", "damaged_returned"])).count()

    # Maintenance
    pending_maint = MaintenanceLog.query.filter(MaintenanceLog.status.in_(["pending", "in_progress"])).count()
    overdue_maint = MaintenanceLog.query.filter(
        MaintenanceLog.status.in_(["pending", "in_progress"]),
        MaintenanceLog.scheduled_date < date.today(),
    ).count()

    # Financials
    total_valuation = db.session.query(func.sum(Asset.purchase_cost)).scalar() or 0
    actual_maint_spent = db.session.query(func.sum(MaintenanceLog.actual_cost)).filter_by(status="resolved").scalar() or 0

    # Recent activities
    activities = []
    for act in ActivityLog.query.order_by(desc(ActivityLog.timestamp)).limit(8).all():
        activities.append({
            "id": act.id,
            "action": act.action,
            "entity": act.entity_type,
            "description": act.description,
            "timestamp": act.timestamp.strftime("%d %b, %I:%M %p") if act.timestamp else "",
        })

    return jsonify({
        "assets": {
            "total": total_assets,
            "active": active_assets,
            "under_repair": repair_assets,
            "damaged": damaged_assets,
            "retired": retired_assets,
            "total_valuation": float(total_valuation),
        },
        "issues": {
            "total": total_issues,
            "active": active_issues,
            "overdue": overdue_issues,
            "returned": returned_issues,
        },
        "maintenance": {
            "pending": pending_maint,
            "overdue": overdue_maint,
            "actual_spent": float(actual_maint_spent),
        },
        "activities": activities,
    })


# ─────────────────────────────────────────────────────────────
# 2. Assets Endpoints (CRUD)
# ─────────────────────────────────────────────────────────────
@api_bp.route("/assets", methods=["GET"])
def get_assets():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    department_id = request.args.get("department_id")
    status = request.args.get("status", "")

    query = Asset.query
    if q:
        query = query.filter(
            or_(
                Asset.name.ilike(f"%{q}%"),
                Asset.asset_tag.ilike(f"%{q}%"),
                Asset.location.ilike(f"%{q}%"),
                Asset.serial_number.ilike(f"%{q}%"),
            )
        )
    if category:
        query = query.filter(Asset.category == category)
    if department_id:
        query = query.filter(Asset.department_id == department_id)
    if status:
        query = query.filter(Asset.status == status)

    assets = query.order_by(desc(Asset.created_at)).all()
    results = []
    for a in assets:
        results.append({
            "id": a.id,
            "asset_tag": a.asset_tag,
            "name": a.name,
            "category": a.category,
            "department_id": a.department_id,
            "department_name": a.department.name if a.department else "N/A",
            "department_code": a.department.code if a.department else "N/A",
            "location": a.location or "",
            "purchase_date": a.purchase_date.strftime("%Y-%m-%d") if a.purchase_date else None,
            "purchase_cost": float(a.purchase_cost or 0),
            "warranty_expiry": a.warranty_expiry.strftime("%Y-%m-%d") if a.warranty_expiry else None,
            "status": a.status,
            "status_label": a.status_label,
            "status_badge_class": a.status_badge_class,
            "condition_rating": a.condition_rating or 5,
            "is_currently_issued": a.is_currently_issued,
            "current_issue": {
                "id": a.current_issue.id,
                "slip_number": a.current_issue.slip_number,
                "issued_to_name": a.current_issue.issued_to_name,
                "issued_to_dept": a.current_issue.issued_to_dept,
                "expected_return_date": a.current_issue.expected_return_date.strftime("%Y-%m-%d %H:%M") if a.current_issue.expected_return_date else None,
                "is_overdue": a.current_issue.is_overdue,
            } if a.current_issue else None,
            "serial_number": a.serial_number or "",
            "manufacturer": a.manufacturer or "",
            "model_number": a.model_number or "",
            "qr_code_path": a.qr_code_path or "",
            "risk_score": a.risk_score,
            "risk_label": risk_label(a.risk_score),
        })

    return jsonify({"assets": results, "count": len(results)})


@api_bp.route("/assets/<int:asset_id>", methods=["GET"])
def get_asset_detail(asset_id):
    a = Asset.query.get_or_404(asset_id)

    # Issue history
    issues_list = []
    for iss in a.issues.order_by(desc(AssetIssue.issue_date)).limit(10).all():
        issues_list.append({
            "id": iss.id,
            "slip_number": iss.slip_number,
            "issued_to_name": iss.issued_to_name,
            "issued_to_id_number": iss.issued_to_id_number,
            "issued_to_dept": iss.issued_to_dept,
            "issuer_name": iss.issuer_name,
            "purpose": iss.purpose,
            "issue_date": iss.issue_date.strftime("%d %b %Y, %I:%M %p") if iss.issue_date else "",
            "expected_return_date": iss.expected_return_date.strftime("%d %b %Y, %I:%M %p") if iss.expected_return_date else "Permanent",
            "actual_return_date": iss.actual_return_date.strftime("%d %b %Y, %I:%M %p") if iss.actual_return_date else None,
            "status": iss.status,
            "status_label": iss.status_label,
            "status_badge_class": iss.status_badge_class,
            "issue_condition": iss.issue_condition,
            "return_condition": iss.return_condition,
        })

    # Maintenance history
    maint_list = []
    for m in a.maintenance_logs.order_by(desc(MaintenanceLog.created_at)).limit(10).all():
        maint_list.append({
            "id": m.id,
            "issue_description": m.issue_description,
            "status": m.status,
            "priority": m.priority,
            "request_date": m.request_date.strftime("%d %b %Y") if m.request_date else "",
            "completed_date": m.completed_date.strftime("%d %b %Y") if m.completed_date else None,
            "actual_cost": float(m.actual_cost or 0),
        })

    return jsonify({
        "asset": {
            "id": a.id,
            "asset_tag": a.asset_tag,
            "name": a.name,
            "category": a.category,
            "department_id": a.department_id,
            "department_name": a.department.name if a.department else "N/A",
            "location": a.location or "",
            "purchase_date": a.purchase_date.strftime("%Y-%m-%d") if a.purchase_date else None,
            "purchase_cost": float(a.purchase_cost or 0),
            "warranty_expiry": a.warranty_expiry.strftime("%Y-%m-%d") if a.warranty_expiry else None,
            "status": a.status,
            "status_label": a.status_label,
            "status_badge_class": a.status_badge_class,
            "condition_rating": a.condition_rating or 5,
            "notes": a.notes or "",
            "serial_number": a.serial_number or "",
            "model_number": a.model_number or "",
            "manufacturer": a.manufacturer or "",
            "qr_code_path": a.qr_code_path or "",
            "book_value": float(current_book_value(a)),
            "est_maintenance_cost": float(estimated_maintenance_cost(a)),
            "est_replacement_cost": float(estimated_replacement_cost(a)),
            "risk_score": a.risk_score,
            "risk_label": risk_label(a.risk_score),
            "is_currently_issued": a.is_currently_issued,
        },
        "issues": issues_list,
        "maintenance": maint_list,
    })


@api_bp.route("/assets", methods=["POST"])
def create_asset():
    data = request.json or request.form
    dept_id = data.get("department_id")
    dept = Department.query.get(dept_id)
    if not dept:
        return jsonify({"error": "Invalid department"}), 400

    tag = data.get("asset_tag") or _generate_asset_tag(dept.code)
    pd_str = data.get("purchase_date")
    we_str = data.get("warranty_expiry")

    asset = Asset(
        asset_tag=tag,
        name=data.get("name", "").strip(),
        category=data.get("category", "Other"),
        department_id=dept_id,
        location=data.get("location", "").strip(),
        purchase_date=datetime.strptime(pd_str, "%Y-%m-%d").date() if pd_str else None,
        purchase_cost=float(data.get("purchase_cost") or 0.0),
        warranty_expiry=datetime.strptime(we_str, "%Y-%m-%d").date() if we_str else None,
        status=data.get("status", "active"),
        condition_rating=int(data.get("condition_rating") or 5),
        serial_number=data.get("serial_number", "").strip(),
        model_number=data.get("model_number", "").strip(),
        manufacturer=data.get("manufacturer", "").strip(),
        notes=data.get("notes", "").strip(),
    )
    db.session.add(asset)
    db.session.flush()

    try:
        qr_path = generate_asset_qr(asset, _get_base_url())
        asset.qr_code_path = qr_path
    except Exception:
        pass

    db.session.commit()
    return jsonify({"success": True, "asset_id": asset.id, "asset_tag": asset.asset_tag}), 201


@api_bp.route("/assets/<int:asset_id>", methods=["PUT"])
def update_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    data = request.json or request.form

    if "name" in data: asset.name = data["name"].strip()
    if "category" in data: asset.category = data["category"]
    if "department_id" in data: asset.department_id = data["department_id"]
    if "location" in data: asset.location = data["location"].strip()
    if "status" in data: asset.status = data["status"]
    if "condition_rating" in data: asset.condition_rating = int(data["condition_rating"])
    if "purchase_cost" in data: asset.purchase_cost = float(data["purchase_cost"] or 0)
    if "serial_number" in data: asset.serial_number = data["serial_number"].strip()
    if "manufacturer" in data: asset.manufacturer = data["manufacturer"].strip()
    if "notes" in data: asset.notes = data["notes"].strip()

    db.session.commit()
    return jsonify({"success": True, "message": "Asset updated successfully"})


@api_bp.route("/assets/<int:asset_id>", methods=["DELETE"])
def delete_asset(asset_id):
    asset = Asset.query.get_or_404(asset_id)
    db.session.delete(asset)
    db.session.commit()
    return jsonify({"success": True, "message": f"Asset {asset.asset_tag} deleted"})


# ─────────────────────────────────────────────────────────────
# 3. Material & Asset Issue Endpoints (Gate Pass / Parchi)
# ─────────────────────────────────────────────────────────────
@api_bp.route("/issues", methods=["GET"])
def get_issues():
    tab = request.args.get("tab", "all")
    q = request.args.get("q", "").strip()

    now = datetime.utcnow()
    query = AssetIssue.query.join(Asset)

    if tab == "active":
        query = query.filter(AssetIssue.status == "issued")
    elif tab == "overdue":
        query = query.filter(
            AssetIssue.status == "issued",
            AssetIssue.expected_return_date.isnot(None),
            AssetIssue.expected_return_date < now,
        )
    elif tab == "returned":
        query = query.filter(AssetIssue.status.in_(["returned", "damaged_returned"]))

    if q:
        query = query.filter(
            or_(
                AssetIssue.slip_number.ilike(f"%{q}%"),
                AssetIssue.issued_to_name.ilike(f"%{q}%"),
                AssetIssue.purpose.ilike(f"%{q}%"),
                Asset.name.ilike(f"%{q}%"),
                Asset.asset_tag.ilike(f"%{q}%"),
            )
        )

    issues = query.order_by(desc(AssetIssue.issue_date)).all()
    results = []
    for iss in issues:
        results.append({
            "id": iss.id,
            "slip_number": iss.slip_number,
            "asset_id": iss.asset_id,
            "asset_tag": iss.asset.asset_tag,
            "asset_name": iss.asset.name,
            "asset_category": iss.asset.category,
            "asset_location": iss.asset.location or "Lab",
            "issued_to_name": iss.issued_to_name,
            "issued_to_id_number": iss.issued_to_id_number or "",
            "issued_to_dept": iss.issued_to_dept or "",
            "issued_to_phone": iss.issued_to_phone or "",
            "issued_to_email": iss.issued_to_email or "",
            "issuer_name": iss.issuer_name or "Staff",
            "purpose": iss.purpose,
            "gate_pass_type": iss.gate_pass_type,
            "issue_date": iss.issue_date.strftime("%d %b %Y, %I:%M %p") if iss.issue_date else "",
            "expected_return_date": iss.expected_return_date.strftime("%d %b %Y, %I:%M %p") if iss.expected_return_date else "Non-Returnable",
            "actual_return_date": iss.actual_return_date.strftime("%d %b %Y, %I:%M %p") if iss.actual_return_date else None,
            "status": iss.status,
            "status_label": iss.status_label,
            "status_badge_class": iss.status_badge_class,
            "is_overdue": iss.is_overdue,
            "issue_condition": iss.issue_condition or "Good",
            "return_condition": iss.return_condition or "",
            "fine_amount": float(iss.fine_amount or 0),
            "remarks_on_issue": iss.remarks_on_issue or "",
            "remarks_on_return": iss.remarks_on_return or "",
        })

    return jsonify({
        "issues": results,
        "count": len(results),
        "active_count": AssetIssue.query.filter_by(status="issued").count(),
        "overdue_count": AssetIssue.query.filter(
            AssetIssue.status == "issued",
            AssetIssue.expected_return_date.isnot(None),
            AssetIssue.expected_return_date < now
        ).count(),
    })


@api_bp.route("/issues", methods=["POST"])
def create_issue():
    data = request.json or request.form
    asset_id = data.get("asset_id")
    asset = Asset.query.get_or_404(asset_id)

    if asset.is_currently_issued:
        return jsonify({
            "error": f"Asset {asset.asset_tag} is already issued (Slip: {asset.current_issue.slip_number})"
        }), 400

    return_dt_str = data.get("expected_return_date")
    expected_dt = None
    if return_dt_str:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                expected_dt = datetime.strptime(return_dt_str, fmt)
                break
            except ValueError:
                pass

    slip_number = _generate_slip_number()
    issuer_name = data.get("issuer_name", "Staff")

    admin_user = User.query.filter_by(role="admin").first()
    issued_by_id = admin_user.id if admin_user else 1

    issue = AssetIssue(
        slip_number=slip_number,
        asset_id=asset.id,
        issued_by_id=issued_by_id,
        issuer_name=issuer_name,
        issued_to_name=data.get("issued_to_name", "").strip(),
        issued_to_id_number=data.get("issued_to_id_number", "").strip(),
        issued_to_dept=data.get("issued_to_dept", "").strip(),
        issued_to_phone=data.get("issued_to_phone", "").strip(),
        issued_to_email=data.get("issued_to_email", "").strip(),
        purpose=data.get("purpose", "").strip(),
        gate_pass_type=data.get("gate_pass_type", "returnable"),
        issue_date=datetime.utcnow(),
        expected_return_date=expected_dt,
        issue_condition=data.get("issue_condition", "Good / Functional"),
        remarks_on_issue=data.get("remarks_on_issue", "").strip(),
        status="issued",
    )

    db.session.add(issue)
    
    # Audit log
    db.session.add(ActivityLog(
        user_id=issued_by_id,
        action="ISSUE_GATE_PASS",
        entity_type="AssetIssue",
        entity_id=issue.id,
        description=f"Gate Pass {slip_number} created: Asset {asset.asset_tag} issued to {issue.issued_to_name}",
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    return jsonify({
        "success": True,
        "issue_id": issue.id,
        "slip_number": issue.slip_number,
        "message": f"Gate Pass #{slip_number} created successfully!",
    }), 201


@api_bp.route("/issues/<int:issue_id>/pdf")
def download_issue_pdf(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    buf = generate_issue_parchi_pdf(issue, _get_base_url())
    return send_file(
        buf,
        download_name=f"GatePass_{issue.slip_number}.pdf",
        as_attachment=True,
        mimetype="application/pdf",
    )


@api_bp.route("/issues/<int:issue_id>/return", methods=["POST"])
def return_issue(issue_id):
    issue = AssetIssue.query.get_or_404(issue_id)
    data = request.json or request.form

    return_condition = data.get("return_condition", "Good / Functional")
    remarks = data.get("remarks_on_return", "").strip()
    fine = float(data.get("fine_amount") or 0.0)

    issue.actual_return_date = datetime.utcnow()
    issue.return_condition = return_condition
    issue.remarks_on_return = remarks
    issue.fine_amount = fine

    if "Damaged" in return_condition or "Faulty" in return_condition:
        issue.status = "damaged_returned"
        issue.asset.status = "damaged"
    else:
        issue.status = "returned"
        if issue.asset.status != "retired":
            issue.asset.status = "active"

    # Audit log
    admin_user = User.query.filter_by(role="admin").first()
    db.session.add(ActivityLog(
        user_id=admin_user.id if admin_user else 1,
        action="RETURN_GATE_PASS",
        entity_type="AssetIssue",
        entity_id=issue.id,
        description=f"Asset {issue.asset.asset_tag} returned by {issue.issued_to_name} (Status: {issue.status})",
        ip_address=request.remote_addr,
    ))

    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"Asset {issue.asset.asset_tag} successfully returned & Gate Pass closed!",
    })


# ─────────────────────────────────────────────────────────────
# 4. Maintenance Endpoints
# ─────────────────────────────────────────────────────────────
@api_bp.route("/maintenance", methods=["GET"])
def get_maintenance():
    logs = MaintenanceLog.query.order_by(desc(MaintenanceLog.created_at)).all()
    results = []
    for m in logs:
        results.append({
            "id": m.id,
            "asset_id": m.asset_id,
            "asset_tag": m.asset.asset_tag if m.asset else "N/A",
            "asset_name": m.asset.name if m.asset else "N/A",
            "issue_description": m.issue_description,
            "status": m.status,
            "priority": m.priority,
            "request_date": m.request_date.strftime("%d %b %Y") if m.request_date else "",
            "scheduled_date": m.scheduled_date.strftime("%d %b %Y") if m.scheduled_date else "",
            "completed_date": m.completed_date.strftime("%d %b %Y") if m.completed_date else None,
            "estimated_cost": float(m.estimated_cost or 0),
            "actual_cost": float(m.actual_cost or 0),
            "technician_notes": m.technician_notes or "",
            "is_overdue": m.is_overdue,
        })
    return jsonify({"maintenance": results, "count": len(results)})


@api_bp.route("/maintenance", methods=["POST"])
def create_maintenance():
    data = request.json or request.form
    asset_id = data.get("asset_id")
    asset = Asset.query.get_or_404(asset_id)

    sched_str = data.get("scheduled_date")
    sched_dt = datetime.strptime(sched_str, "%Y-%m-%d").date() if sched_str else None

    admin_user = User.query.filter_by(role="admin").first()
    user_id = admin_user.id if admin_user else 1

    log = MaintenanceLog(
        asset_id=asset.id,
        requested_by_id=user_id,
        issue_description=data.get("issue_description", "").strip(),
        priority=data.get("priority", "medium"),
        scheduled_date=sched_dt,
        estimated_cost=float(data.get("estimated_cost") or 0.0),
        status="pending",
    )
    asset.status = "under_repair"
    db.session.add(log)
    db.session.commit()

    return jsonify({"success": True, "log_id": log.id, "message": "Maintenance request logged!"}), 201


# ─────────────────────────────────────────────────────────────
# 5. Orders & Procurement Endpoints
# ─────────────────────────────────────────────────────────────
@api_bp.route("/orders", methods=["GET"])
def get_orders():
    orders = AssetOrder.query.order_by(desc(AssetOrder.created_at)).all()
    results = []
    for o in orders:
        results.append({
            "id": o.id,
            "order_number": o.order_number,
            "item_name": o.item_name,
            "category": o.category,
            "department_id": o.department_id,
            "department_name": o.department.name if o.department else "N/A",
            "quantity": o.quantity,
            "estimated_unit_cost": float(o.estimated_unit_cost or 0),
            "total_cost": float(o.total_cost or 0),
            "priority": o.priority,
            "status": o.status,
            "supplier_name": o.supplier_name or "",
            "justification": o.justification or "",
            "specs_notes": o.specs_notes or "",
            "order_date": o.order_date.strftime("%d %b %Y") if o.order_date else "",
        })
    return jsonify({"orders": results, "count": len(results)})


@api_bp.route("/orders", methods=["POST"])
def create_order():
    data = request.json or request.form
    qty = int(data.get("quantity") or 1)
    unit_cost = float(data.get("estimated_unit_cost") or 0.0)

    admin_user = User.query.filter_by(role="admin").first()
    user_id = admin_user.id if admin_user else 1

    order_no = _generate_order_number()
    order = AssetOrder(
        order_number=order_no,
        item_name=data.get("item_name", "").strip(),
        category=data.get("category", "Other"),
        department_id=int(data.get("department_id") or 1),
        requested_by_id=user_id,
        quantity=qty,
        estimated_unit_cost=unit_cost,
        total_cost=qty * unit_cost,
        priority=data.get("priority", "medium"),
        status="pending",
        supplier_name=data.get("supplier_name", "").strip(),
        justification=data.get("justification", "").strip(),
        specs_notes=data.get("specs_notes", "").strip(),
        order_date=date.today(),
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({"success": True, "order_number": order_no, "message": "Order requisition created!"}), 201


@api_bp.route("/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    order = AssetOrder.query.get_or_404(order_id)
    data = request.json or request.form
    new_status = data.get("status")
    if new_status in ["pending", "approved", "ordered", "received", "cancelled"]:
        order.status = new_status
        db.session.commit()
    return jsonify({"success": True, "message": f"Order marked as {new_status}"})


# ─────────────────────────────────────────────────────────────
# 6. Metadata & Utility Endpoints
# ─────────────────────────────────────────────────────────────
@api_bp.route("/departments")
def get_departments():
    depts = Department.query.order_by(Department.name).all()
    results = [{"id": d.id, "name": d.name, "code": d.code, "budget": float(d.budget_allocated or 0)} for d in depts]
    return jsonify({"departments": results})


@api_bp.route("/lookup/<path:identifier>")
def lookup_asset(identifier):
    identifier = identifier.strip().strip("/")
    asset = None
    if identifier.isdigit():
        asset = Asset.query.get(int(identifier))
    if not asset:
        asset = Asset.query.filter(Asset.asset_tag.ilike(identifier)).first()
    if not asset and "assets/" in identifier:
        part = identifier.split("assets/")[-1].split("/")[0].split("?")[0]
        if part.isdigit():
            asset = Asset.query.get(int(part))

    if not asset:
        return jsonify({"found": False, "error": "Asset not found"}), 404

    return jsonify({
        "found": True,
        "asset": {
            "id": asset.id,
            "asset_tag": asset.asset_tag,
            "name": asset.name,
            "category": asset.category,
            "department": asset.department.name if asset.department else "N/A",
            "location": asset.location or "Lab",
            "status": asset.status,
            "status_label": asset.status_label,
            "is_currently_issued": asset.is_currently_issued,
            "current_issue": {
                "id": asset.current_issue.id,
                "slip_number": asset.current_issue.slip_number,
                "issued_to_name": asset.current_issue.issued_to_name,
            } if asset.current_issue else None,
        }
    })


# ─────────────────────────────────────────────────────────────
# 7. Budget & Financial Endpoints
# ─────────────────────────────────────────────────────────────
@api_bp.route("/budget", methods=["GET"])
def get_budget():
    depts = Department.query.all()
    dept_budgets = []
    total_allocated = 0
    total_spent = 0
    total_est_maint = 0
    total_est_repl = 0

    for d in depts:
        alloc = float(d.budget_allocated or 0)
        total_allocated += alloc
        
        # Calculate maintenance actual spent
        maint_cost = db.session.query(func.sum(MaintenanceLog.actual_cost)).join(Asset).filter(
            Asset.department_id == d.id,
            MaintenanceLog.status == "resolved"
        ).scalar() or 0
        
        # Calculate procurement spent
        order_cost = db.session.query(func.sum(AssetOrder.total_cost)).filter(
            AssetOrder.department_id == d.id,
            AssetOrder.status.in_(["ordered", "received"])
        ).scalar() or 0
        
        spent = float(maint_cost) + float(order_cost)
        total_spent += spent

        # Department assets sum
        assets_in_dept = Asset.query.filter_by(department_id=d.id).all()
        dept_maint_est = sum(estimated_maintenance_cost(a) for a in assets_in_dept)
        dept_repl_est = sum(estimated_replacement_cost(a) for a in assets_in_dept)
        total_est_maint += dept_maint_est
        total_est_repl += dept_repl_est

        dept_budgets.append({
            "department_id": d.id,
            "department_name": d.name,
            "code": d.code,
            "allocated": alloc,
            "spent": spent,
            "remaining": alloc - spent,
            "utilization_pct": round((spent / alloc * 100), 1) if alloc > 0 else 0,
            "est_maintenance": float(dept_maint_est),
            "est_replacement": float(dept_repl_est),
            "asset_count": len(assets_in_dept),
        })

    estimates = BudgetEstimate.query.order_by(desc(BudgetEstimate.fiscal_year)).all()
    estimates_list = []
    for e in estimates:
        estimates_list.append({
            "id": e.id,
            "fiscal_year": e.fiscal_year,
            "department_id": e.department_id,
            "department_name": e.department.name if e.department else "N/A",
            "category": e.category or "General",
            "estimated_maintenance_cost": float(e.estimated_maintenance_cost or 0),
            "estimated_replacement_cost": float(e.estimated_replacement_cost or 0),
            "total_estimated": float(e.total_estimated),
            "actual_spent": float(e.actual_spent or 0),
            "variance": float(e.variance),
            "prepared_date": e.prepared_date.strftime("%d %b %Y") if e.prepared_date else "",
            "notes": e.notes or "",
        })

    return jsonify({
        "summary": {
            "total_allocated": total_allocated,
            "total_spent": total_spent,
            "total_remaining": total_allocated - total_spent,
            "utilization_pct": round((total_spent / total_allocated * 100), 1) if total_allocated > 0 else 0,
            "total_est_maint": float(total_est_maint),
            "total_est_repl": float(total_est_repl),
        },
        "departments": dept_budgets,
        "estimates": estimates_list,
    })


@api_bp.route("/budget/allocate", methods=["POST"])
def update_department_budget():
    data = request.json or request.form
    dept_id = data.get("department_id")
    amount = float(data.get("budget_allocated") or 0.0)
    dept = Department.query.get_or_404(dept_id)
    dept.budget_allocated = amount
    db.session.commit()
    return jsonify({"success": True, "message": f"Budget for {dept.name} updated to ₹{amount:,.2f}"})


# ─────────────────────────────────────────────────────────────
# 8. Allocation History & Transfers
# ─────────────────────────────────────────────────────────────
@api_bp.route("/allocations", methods=["GET"])
def get_allocations():
    logs = AllocationHistory.query.order_by(desc(AllocationHistory.allocation_date)).all()
    results = []
    for l in logs:
        results.append({
            "id": l.id,
            "asset_id": l.asset_id,
            "asset_tag": l.asset.asset_tag if l.asset else "N/A",
            "asset_name": l.asset.name if l.asset else "N/A",
            "from_dept": l.from_department.name if l.from_department else "Central Inventory",
            "to_dept": l.to_department.name if l.to_department else "Central Inventory",
            "from_user": l.from_user.full_name if l.from_user else "N/A",
            "to_user": l.to_user.full_name if l.to_user else "N/A",
            "allocated_by": l.allocated_by.full_name if l.allocated_by else "Admin",
            "allocation_date": l.allocation_date.strftime("%d %b %Y") if l.allocation_date else "",
            "return_date": l.return_date.strftime("%d %b %Y") if l.return_date else None,
            "reason": l.reason or "",
            "notes": l.notes or "",
        })
    return jsonify({"allocations": results, "count": len(results)})


@api_bp.route("/allocations", methods=["POST"])
def create_allocation():
    data = request.json or request.form
    asset_id = data.get("asset_id")
    asset = Asset.query.get_or_404(asset_id)
    
    to_dept_id = data.get("to_department_id")
    to_user_id = data.get("to_user_id")
    reason = data.get("reason", "").strip()
    notes = data.get("notes", "").strip()

    admin_user = User.query.filter_by(role="admin").first()
    admin_id = admin_user.id if admin_user else 1

    alloc = AllocationHistory(
        asset_id=asset.id,
        from_department_id=asset.department_id,
        to_department_id=to_dept_id or asset.department_id,
        from_user_id=asset.assigned_to_id,
        to_user_id=to_user_id if to_user_id else None,
        allocated_by_id=admin_id,
        allocation_date=date.today(),
        reason=reason,
        notes=notes,
    )
    if to_dept_id:
        asset.department_id = to_dept_id
    if to_user_id:
        asset.assigned_to_id = to_user_id

    db.session.add(alloc)
    db.session.commit()
    return jsonify({"success": True, "message": f"Asset {asset.asset_tag} successfully transferred!"}), 201


# ─────────────────────────────────────────────────────────────
# 9. Predictive Analysis & Risk Intelligence
# ─────────────────────────────────────────────────────────────
@api_bp.route("/analysis", methods=["GET"])
def get_analysis():
    assets = Asset.query.all()
    total_val = sum(float(a.purchase_cost or 0) for a in assets)
    total_book_val = sum(current_book_value(a) for a in assets)
    total_est_maint = sum(estimated_maintenance_cost(a) for a in assets)
    total_est_repl = sum(estimated_replacement_cost(a) for a in assets)

    # Risk Distribution
    risk_low = 0
    risk_medium = 0
    risk_high = 0
    risk_critical = 0

    category_counts = {}
    high_risk_assets = []

    for a in assets:
        score = a.risk_score
        if score >= 75:
            risk_critical += 1
            high_risk_assets.append({
                "id": a.id,
                "asset_tag": a.asset_tag,
                "name": a.name,
                "category": a.category,
                "department": a.department.name if a.department else "N/A",
                "risk_score": score,
                "risk_label": "Critical",
                "age_years": a.age_years,
                "repair_count": a.repair_count,
                "purchase_cost": float(a.purchase_cost or 0),
                "book_value": float(current_book_value(a)),
                "est_replacement_cost": float(estimated_replacement_cost(a)),
            })
        elif score >= 50:
            risk_high += 1
            if len(high_risk_assets) < 15:
                high_risk_assets.append({
                    "id": a.id,
                    "asset_tag": a.asset_tag,
                    "name": a.name,
                    "category": a.category,
                    "department": a.department.name if a.department else "N/A",
                    "risk_score": score,
                    "risk_label": "High",
                    "age_years": a.age_years,
                    "repair_count": a.repair_count,
                    "purchase_cost": float(a.purchase_cost or 0),
                    "book_value": float(current_book_value(a)),
                    "est_replacement_cost": float(estimated_replacement_cost(a)),
                })
        elif score >= 25:
            risk_medium += 1
        else:
            risk_low += 1

        cat = a.category or "Other"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    high_risk_assets.sort(key=lambda x: x["risk_score"], reverse=True)

    return jsonify({
        "metrics": {
            "total_assets": len(assets),
            "total_original_cost": total_val,
            "total_current_book_value": total_book_val,
            "total_depreciation": total_val - total_book_val,
            "total_est_maintenance_liability": total_est_maint,
            "total_est_replacement_need": total_est_repl,
        },
        "risk_breakdown": {
            "low": risk_low,
            "medium": risk_medium,
            "high": risk_high,
            "critical": risk_critical,
        },
        "category_distribution": category_counts,
        "high_risk_assets": high_risk_assets,
    })


# ─────────────────────────────────────────────────────────────
# 10. Reports & Print Grid
# ─────────────────────────────────────────────────────────────
@api_bp.route("/reports/labels", methods=["GET"])
def get_report_labels():
    dept_id = request.args.get("department_id")
    category = request.args.get("category")
    
    query = Asset.query
    if dept_id: query = query.filter(Asset.department_id == dept_id)
    if category: query = query.filter(Asset.category == category)
    
    assets = query.order_by(Asset.asset_tag).all()
    labels = []
    base_url = _get_base_url()

    for a in assets:
        labels.append({
            "id": a.id,
            "asset_tag": a.asset_tag,
            "name": a.name,
            "category": a.category,
            "department": a.department.name if a.department else "N/A",
            "department_code": a.department.code if a.department else "",
            "location": a.location or "",
            "qr_url": f"{base_url}/assets/{a.id}",
        })
    return jsonify({"labels": labels, "count": len(labels)})


# ─────────────────────────────────────────────────────────────
# 11. Auth & Users API
# ─────────────────────────────────────────────────────────────
@api_bp.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.json or request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter(or_(User.username == username, User.email == username)).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid username or password"}), 401

    user.last_login = datetime.utcnow()
    db.session.add(ActivityLog(
        user_id=user.id,
        action="USER_LOGIN",
        entity_type="User",
        entity_id=user.id,
        description=f"User {user.username} signed in successfully",
        ip_address=request.remote_addr,
    ))
    db.session.commit()

    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name or user.username,
            "email": user.email,
            "role": user.role,
            "department_id": user.department_id,
            "department_name": user.department.name if user.department else "Admin HQ",
        }
    })


@api_bp.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.json or request.form
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    full_name = data.get("full_name", "").strip()
    dept_id = data.get("department_id")
    role = data.get("role", "department")

    if not username or not email or not password:
        return jsonify({"error": "Missing required fields"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    user = User(
        username=username,
        email=email,
        full_name=full_name or username,
        department_id=dept_id if dept_id else None,
        role=role,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "Account created successfully!"}), 201


@api_bp.route("/auth/logs", methods=["GET"])
def get_audit_logs():
    logs = ActivityLog.query.order_by(desc(ActivityLog.timestamp)).limit(50).all()
    results = []
    for l in logs:
        results.append({
            "id": l.id,
            "user": l.user.username if l.user else "System",
            "action": l.action,
            "entity": l.entity_type,
            "description": l.description,
            "ip_address": l.ip_address,
            "timestamp": l.timestamp.strftime("%d %b %Y, %I:%M:%S %p") if l.timestamp else "",
        })
    return jsonify({"logs": results})

