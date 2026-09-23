"""
Auth Blueprint — Login, Logout, Registration, Password Reset & User Management
"""
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from app.blueprints.auth import auth_bp
from app.extensions import db
from app.models import User, Department
from app.utils.decorators import admin_required, log_activity


def get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_activity("LOGIN", "User", user.id, f"{user.username} logged in")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard.index"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        dept_id = request.form.get("department_id") or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Form validation
        if not full_name or not username or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("auth/register.html", departments=departments, form=request.form)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("auth/register.html", departments=departments, form=request.form)

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter.", "danger")
            return render_template("auth/register.html", departments=departments, form=request.form)

        if User.query.filter_by(username=username).first():
            flash("Username is already taken. Please choose another.", "danger")
            return render_template("auth/register.html", departments=departments, form=request.form)

        if User.query.filter_by(email=email).first():
            flash("Email address is already registered.", "danger")
            return render_template("auth/register.html", departments=departments, form=request.form)

        # Create user (Default role: department staff)
        user = User(
            full_name=full_name,
            username=username,
            email=email,
            role="department",
            department_id=dept_id if dept_id else None,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_activity("REGISTER", "User", user.id, f"User {username} registered account")
        flash("Registration successful! You can now sign in with your credentials.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", departments=departments, form={})


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    reset_token = None
    reset_url = None

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if user:
            s = get_serializer()
            reset_token = s.dumps(user.email, salt="password-reset-salt")
            reset_url = url_for("auth.reset_password", token=reset_token, _external=True)
            log_activity("FORGOT_PASSWORD", "User", user.id, f"Password reset requested for {user.username}")
            flash("Account verified! Click the reset button below to set your new password.", "success")
        else:
            flash("No account found with that username or email address.", "danger")

    return render_template("auth/forgot_password.html", reset_token=reset_token, reset_url=reset_url)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    s = get_serializer()
    try:
        email = s.loads(token, salt="password-reset-salt", max_age=3600)
    except SignatureExpired:
        flash("Password reset link has expired. Please request a new one.", "warning")
        return redirect(url_for("auth.forgot_password"))
    except BadTimeSignature:
        flash("Invalid password reset token.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=email).first_or_404()

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("auth/reset_password.html", token=token, user=user)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html", token=token, user=user)

        user.set_password(password)
        db.session.commit()
        log_activity("RESET_PASSWORD", "User", user.id, f"Password reset completed for {user.username}")
        flash("Your password has been reset successfully! Please log in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token, user=user)


@auth_bp.route("/logout")
@login_required
def logout():
    log_activity("LOGOUT", "User", current_user.id, f"{current_user.username} logged out")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/users")
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()
    return render_template("auth/users.html", users=users, departments=departments)


@auth_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    departments = Department.query.order_by(Department.name).all()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "department")
        dept_id = request.form.get("department_id") or None
        password = request.form.get("password", "")

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return render_template("auth/user_form.html", departments=departments, form=request.form)
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("auth/user_form.html", departments=departments, form=request.form)

        user = User(
            username=username, email=email, full_name=full_name,
            role=role, department_id=dept_id if dept_id else None,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_activity("CREATE", "User", user.id, f"Created user {username}")
        flash(f"User '{username}' created successfully.", "success")
        return redirect(url_for("auth.users"))

    return render_template("auth/user_form.html", departments=departments, form={}, user=None)


@auth_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    departments = Department.query.order_by(Department.name).all()
    if request.method == "POST":
        user.full_name = request.form.get("full_name", user.full_name).strip()
        user.email = request.form.get("email", user.email).strip()
        user.role = request.form.get("role", user.role)
        dept_id = request.form.get("department_id") or None
        user.department_id = dept_id
        user.is_active = bool(request.form.get("is_active"))
        new_pw = request.form.get("password", "")
        if new_pw:
            user.set_password(new_pw)
        db.session.commit()
        log_activity("UPDATE", "User", user.id, f"Updated user {user.username}")
        flash("User updated successfully.", "success")
        return redirect(url_for("auth.users"))
    return render_template("auth/user_form.html", departments=departments, user=user, form=user)


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("auth.users"))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    log_activity("DELETE", "User", user_id, f"Deleted user {username}")
    flash(f"User '{username}' deleted.", "success")
    return redirect(url_for("auth.users"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", current_user.full_name).strip()
        current_user.email = request.form.get("email", current_user.email).strip()
        new_pw = request.form.get("new_password", "")
        if new_pw:
            current_pw = request.form.get("current_password", "")
            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "danger")
                return render_template("auth/profile.html")
            current_user.set_password(new_pw)
        db.session.commit()
        flash("Profile updated successfully.", "success")
    return render_template("auth/profile.html")


@auth_bp.route("/audit-logs")
@login_required
@admin_required
def audit_logs():
    from app.models import ActivityLog
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "")
    
    query = ActivityLog.query
    if action_filter:
        query = query.filter(ActivityLog.action == action_filter)
        
    logs = query.order_by(ActivityLog.timestamp.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("auth/audit_logs.html", logs=logs, action_filter=action_filter)


