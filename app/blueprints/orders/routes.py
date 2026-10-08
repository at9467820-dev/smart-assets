"""
AssetPulse — Procurement & New Asset Orders Blueprint
Handles requisitions for ordering new assets, spare parts, and material procurement requests.
"""
from datetime import datetime, date
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app.blueprints.orders import orders_bp
from app.extensions import db
from app.models import AssetOrder, Department, User
from app.utils.decorators import log_activity


def _generate_order_number() -> str:
    """Generate sequential order number like ORD-2026-0001."""
    year = date.today().year
    count = db.session.query(func.count(AssetOrder.id)).scalar() or 0
    return f"ORD-{year}-{count + 1:04d}"


@orders_bp.route("/")
@login_required
def list_orders():
    page = request.args.get("page", 1, type=int)
    status_filter = request.args.get("status", "")
    priority_filter = request.args.get("priority", "")
    dept_filter = request.args.get("department", "")

    query = AssetOrder.query

    if current_user.is_department:
        query = query.filter_by(department_id=current_user.department_id)
    elif dept_filter and current_user.is_admin:
        query = query.filter_by(department_id=dept_filter)

    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)

    orders = query.order_by(AssetOrder.created_at.desc()).paginate(page=page, per_page=20)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "orders/list.html",
        orders=orders,
        departments=departments,
        status_filter=status_filter,
        priority_filter=priority_filter,
        dept_filter=dept_filter,
    )


@orders_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        dept_id = request.form.get("department_id", type=int)
        if current_user.is_department:
            dept_id = current_user.department_id

        qty = int(request.form.get("quantity") or 1)
        unit_cost = float(request.form.get("estimated_unit_cost") or 0.0)
        total_cost = qty * unit_cost

        order_no = _generate_order_number()
        order = AssetOrder(
            order_number=order_no,
            item_name=request.form.get("item_name", "").strip(),
            category=request.form.get("category", "Other"),
            department_id=dept_id,
            requested_by_id=current_user.id,
            quantity=qty,
            estimated_unit_cost=unit_cost,
            total_cost=total_cost,
            priority=request.form.get("priority", "medium"),
            status="pending",
            supplier_name=request.form.get("supplier_name", "").strip(),
            justification=request.form.get("justification", "").strip(),
            specs_notes=request.form.get("specs_notes", "").strip(),
            order_date=date.today(),
        )

        db.session.add(order)
        db.session.commit()

        log_activity("CREATE", "AssetOrder", order.id, f"Requisition #{order_no} created for {order.item_name}")
        flash(f"Purchase Requisition #{order_no} for '{order.item_name}' submitted successfully.", "success")
        return redirect(url_for("orders.list_orders"))

    return render_template("orders/form.html", departments=departments)


@orders_bp.route("/<int:order_id>/update-status", methods=["POST"])
@login_required
def update_status(order_id):
    if not (current_user.is_admin or current_user.is_maintenance):
        flash("Only administrative staff can update order status.", "danger")
        return redirect(url_for("orders.list_orders"))

    order = AssetOrder.query.get_or_404(order_id)
    new_status = request.form.get("status")

    if new_status in ["pending", "approved", "ordered", "received", "cancelled"]:
        order.status = new_status
        if new_status == "received":
            order.delivery_date = date.today()
        db.session.commit()
        log_activity("UPDATE", "AssetOrder", order.id, f"Order #{order.order_number} status changed to {new_status}")
        flash(f"Order #{order.order_number} marked as '{new_status.title()}'.", "success")

    return redirect(url_for("orders.list_orders"))
