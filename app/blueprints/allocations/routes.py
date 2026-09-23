"""
Allocations Blueprint — View allocation history across all assets.
"""
from flask import render_template, request
from flask_login import login_required, current_user
from app.blueprints.allocations import allocations_bp
from app.models import AllocationHistory, Department, Asset


@allocations_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    dept_filter = request.args.get("department", "")

    query = AllocationHistory.query.join(Asset)

    if current_user.is_department:
        query = query.filter(
            (AllocationHistory.from_department_id == current_user.department_id) |
            (AllocationHistory.to_department_id == current_user.department_id)
        )

    if dept_filter:
        query = query.filter(
            (AllocationHistory.from_department_id == dept_filter) |
            (AllocationHistory.to_department_id == dept_filter)
        )

    allocations = query.order_by(AllocationHistory.created_at.desc()).paginate(page=page, per_page=25)
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "allocations/index.html",
        allocations=allocations,
        departments=departments,
        dept_filter=dept_filter,
    )
