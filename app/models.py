"""
AssetPulse — SQLAlchemy Models
All database models for the SAMS application.
"""
from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


# ─────────────────────────────────────────────────────────────
# Department
# ─────────────────────────────────────────────────────────────
class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)  # CSE, ECE, etc.
    head_name = db.Column(db.String(120))
    budget_allocated = db.Column(db.Numeric(12, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship("User", back_populates="department", lazy="dynamic")
    assets = db.relationship("Asset", back_populates="department", lazy="dynamic")
    budget_estimates = db.relationship("BudgetEstimate", back_populates="department", lazy="dynamic")

    def __repr__(self):
        return f"<Department {self.code}>"

    @property
    def asset_count(self):
        return self.assets.count()


# ─────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True, index=True)
    email = db.Column(db.String(200), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(150))
    role = db.Column(
        db.Enum("admin", "department", "maintenance", name="user_roles"),
        nullable=False,
        default="department",
    )
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Relationships
    department = db.relationship("Department", back_populates="users")
    activity_logs = db.relationship("ActivityLog", back_populates="user", lazy="dynamic")
    requested_maintenance = db.relationship(
        "MaintenanceLog", foreign_keys="MaintenanceLog.requested_by_id", back_populates="requested_by", lazy="dynamic"
    )
    assigned_maintenance = db.relationship(
        "MaintenanceLog", foreign_keys="MaintenanceLog.assigned_to_id", back_populates="assigned_to", lazy="dynamic"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_maintenance(self):
        return self.role == "maintenance"

    @property
    def is_department(self):
        return self.role == "department"

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


# ─────────────────────────────────────────────────────────────
# Asset
# ─────────────────────────────────────────────────────────────
class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(50), nullable=False, unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(
        db.Enum(
            "Computer", "Projector", "Furniture", "Lab Equipment",
            "Networking", "Electrical", "HVAC", "Vehicle", "Other",
            name="asset_categories",
        ),
        nullable=False,
        default="Other",
    )
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    location = db.Column(db.String(200))
    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Numeric(12, 2), default=0.00)
    warranty_expiry = db.Column(db.Date)
    status = db.Column(
        db.Enum("active", "under_repair", "damaged", "retired", name="asset_statuses"),
        nullable=False,
        default="active",
    )
    condition_rating = db.Column(db.Integer, default=5)  # 1–10
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    photo_path = db.Column(db.String(300))
    qr_code_path = db.Column(db.String(300))
    notes = db.Column(db.Text)
    serial_number = db.Column(db.String(100))
    model_number = db.Column(db.String(100))
    manufacturer = db.Column(db.String(150))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    department = db.relationship("Department", back_populates="assets")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id])
    maintenance_logs = db.relationship("MaintenanceLog", back_populates="asset", lazy="dynamic", cascade="all, delete-orphan")
    allocation_history = db.relationship("AllocationHistory", back_populates="asset", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Asset {self.asset_tag}: {self.name}>"

    @property
    def age_years(self):
        if self.purchase_date:
            delta = date.today() - self.purchase_date
            return round(delta.days / 365.25, 1)
        return 0

    @property
    def warranty_status(self):
        if not self.warranty_expiry:
            return "unknown"
        today = date.today()
        days_left = (self.warranty_expiry - today).days
        if days_left < 0:
            return "expired"
        elif days_left <= 30:
            return "expiring_soon"
        return "valid"

    @property
    def repair_count(self):
        return self.maintenance_logs.filter_by(status="resolved").count()

    @property
    def days_since_last_service(self):
        last = (
            self.maintenance_logs
            .filter_by(status="resolved")
            .order_by(MaintenanceLog.completed_date.desc())
            .first()
        )
        if last and last.completed_date:
            return (date.today() - last.completed_date).days
        if self.purchase_date:
            return (date.today() - self.purchase_date).days
        return 9999

    @property
    def risk_score(self):
        """0–100 risk score based on age, repair count, days since service."""
        from app.utils.cost_estimator import compute_risk_score
        return compute_risk_score(self)

    @property
    def status_label(self):
        labels = {
            "active": "Active",
            "under_repair": "Under Repair",
            "damaged": "Damaged",
            "retired": "Retired",
        }
        return labels.get(self.status, self.status)

    @property
    def status_badge_class(self):
        classes = {
            "active": "badge-success",
            "under_repair": "badge-warning",
            "damaged": "badge-danger",
            "retired": "badge-secondary",
        }
        return classes.get(self.status, "badge-secondary")


# ─────────────────────────────────────────────────────────────
# MaintenanceLog
# ─────────────────────────────────────────────────────────────
class MaintenanceLog(db.Model):
    __tablename__ = "maintenance_logs"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    request_date = db.Column(db.Date, default=date.today)
    scheduled_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    status = db.Column(
        db.Enum("pending", "in_progress", "resolved", "cancelled", name="maint_statuses"),
        nullable=False,
        default="pending",
    )
    priority = db.Column(
        db.Enum("low", "medium", "high", "critical", name="maint_priorities"),
        default="medium",
    )
    issue_description = db.Column(db.Text, nullable=False)
    technician_notes = db.Column(db.Text)
    estimated_cost = db.Column(db.Numeric(10, 2), default=0.00)
    actual_cost = db.Column(db.Numeric(10, 2), default=0.00)
    next_due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    asset = db.relationship("Asset", back_populates="maintenance_logs")
    requested_by = db.relationship("User", foreign_keys=[requested_by_id], back_populates="requested_maintenance")
    assigned_to = db.relationship("User", foreign_keys=[assigned_to_id], back_populates="assigned_maintenance")

    def __repr__(self):
        return f"<MaintenanceLog #{self.id} [{self.status}]>"

    @property
    def is_overdue(self):
        if self.status in ("pending", "in_progress") and self.scheduled_date:
            return date.today() > self.scheduled_date
        return False


# ─────────────────────────────────────────────────────────────
# AllocationHistory
# ─────────────────────────────────────────────────────────────
class AllocationHistory(db.Model):
    __tablename__ = "allocation_history"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("assets.id"), nullable=False)
    from_department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    to_department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    allocated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    allocation_date = db.Column(db.Date, default=date.today)
    return_date = db.Column(db.Date)
    reason = db.Column(db.String(300))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    asset = db.relationship("Asset", back_populates="allocation_history")
    from_department = db.relationship("Department", foreign_keys=[from_department_id])
    to_department = db.relationship("Department", foreign_keys=[to_department_id])
    from_user = db.relationship("User", foreign_keys=[from_user_id])
    to_user = db.relationship("User", foreign_keys=[to_user_id])
    allocated_by = db.relationship("User", foreign_keys=[allocated_by_id])

    def __repr__(self):
        return f"<AllocationHistory #{self.id}>"


# ─────────────────────────────────────────────────────────────
# BudgetEstimate
# ─────────────────────────────────────────────────────────────
class BudgetEstimate(db.Model):
    __tablename__ = "budget_estimates"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(100))
    estimated_maintenance_cost = db.Column(db.Numeric(12, 2), default=0.00)
    estimated_replacement_cost = db.Column(db.Numeric(12, 2), default=0.00)
    actual_spent = db.Column(db.Numeric(12, 2), default=0.00)
    prepared_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    prepared_date = db.Column(db.Date, default=date.today)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    department = db.relationship("Department", back_populates="budget_estimates")
    prepared_by = db.relationship("User", foreign_keys=[prepared_by_id])

    def __repr__(self):
        return f"<BudgetEstimate dept={self.department_id} FY={self.fiscal_year}>"

    @property
    def total_estimated(self):
        return float(self.estimated_maintenance_cost or 0) + float(self.estimated_replacement_cost or 0)

    @property
    def variance(self):
        return float(self.actual_spent or 0) - self.total_estimated


# ─────────────────────────────────────────────────────────────
# ActivityLog  (Audit Trail)
# ─────────────────────────────────────────────────────────────
class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # e.g. CREATE, UPDATE, DELETE
    entity_type = db.Column(db.String(80))              # e.g. Asset, MaintenanceLog
    entity_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = db.relationship("User", back_populates="activity_logs")

    def __repr__(self):
        return f"<ActivityLog {self.action} on {self.entity_type}#{self.entity_id}>"
