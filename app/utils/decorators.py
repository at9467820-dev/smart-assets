"""
Role-based access decorators for AssetPulse.
"""
from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user


def role_required(*roles):
    """Restrict a view to users with one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    return role_required("admin")(f)


def log_activity(action, entity_type, entity_id, description=""):
    """Helper to write an ActivityLog entry."""
    from flask import request
    from app.extensions import db
    from app.models import ActivityLog
    try:
        log = ActivityLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass  # Never let logging break the main flow
