"""
AssetPulse — Database Seeder
Populates the database with:
  - 6 departments (CSE, ECE, MECH, CIVIL, LIB, ADMIN)
  - 3 users (admin, dept staff, maintenance staff)
  - 45+ realistic assets spread across departments with varied statuses
  - Maintenance logs (some pending/in-progress/resolved)
  - Allocation history entries
  - Budget estimate entries

Run:  python seed.py
"""
import os
import sys
from datetime import date, timedelta
import random

# Ensure app module is importable
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models import (
    Department, User, Asset, MaintenanceLog, AllocationHistory, BudgetEstimate, ActivityLog
)

app = create_app("development")

# ── Helpers ────────────────────────────────────────────────────────
def rand_date(start_year=2018, end_year=2024):
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    return start + timedelta(days=random.randint(0, (end - start).days))

def warranty_date(purchase_date, years=3):
    return date(purchase_date.year + years, purchase_date.month, purchase_date.day)

# ── Seed Data ────────────────────────────────────────────────────
DEPARTMENTS = [
    {"name": "Computer Science & Engineering", "code": "CSE", "head_name": "Dr. Ramesh Kumar", "budget_allocated": 500000},
    {"name": "Electronics & Communication",    "code": "ECE", "head_name": "Dr. Priya Nair",   "budget_allocated": 450000},
    {"name": "Mechanical Engineering",          "code": "MECH","head_name": "Dr. Arvind Singh", "budget_allocated": 400000},
    {"name": "Civil Engineering",               "code": "CIVIL","head_name":"Dr. Meena Sharma", "budget_allocated": 350000},
    {"name": "Library",                         "code": "LIB", "head_name": "Mr. Suresh Babu",  "budget_allocated": 150000},
    {"name": "Administration & BBA",            "code": "ADMIN","head_name":"Ms. Anita Rao",    "budget_allocated": 200000},
]

ASSETS_SEED = [
    # CSE
    ("Dell Optiplex 7090 Desktop", "Computer",     "CSE", "CS Lab 1, Block A",   45000,  "2021-03-15", 3, "active",     8),
    ("HP ProBook 450 G8 Laptop",   "Computer",     "CSE", "CS Lab 1, Block A",   58000,  "2022-06-10", 3, "active",     9),
    ("Lenovo ThinkPad E14",        "Computer",     "CSE", "Faculty Room, Block A",62000,  "2023-01-20", 3, "active",     9),
    ("BenQ 24\" Monitor (x4)",     "Computer",     "CSE", "CS Lab 2, Block A",   18000,  "2021-07-05", 3, "under_repair",6),
    ("Cisco 24-Port Switch",       "Networking",   "CSE", "Server Room, Block A", 32000,  "2020-09-12", 5, "active",     7),
    ("Epson EB-X41 Projector",     "Projector",    "CSE", "Seminar Hall A1",     28000,  "2019-11-08", 3, "damaged",    4),
    ("APC Smart UPS 2200VA",       "Electrical",   "CSE", "Server Room, Block A", 35000,  "2020-04-18", 5, "active",     6),
    ("Dell PowerEdge T40 Server",  "Computer",     "CSE", "Server Room, Block A", 95000,  "2022-08-25", 5, "active",     9),
    ("HP LaserJet Pro M404n",      "Other",        "CSE", "CS Lab 1, Block A",   22000,  "2021-09-30", 3, "active",     7),
    ("Wooden Workbench (x6)",      "Furniture",    "CSE", "CS Lab 2, Block A",   8000,   "2018-06-01", 7, "retired",    3),

    # ECE
    ("Rigol DS1054Z Oscilloscope", "Lab Equipment","ECE", "Electronics Lab, Block B",48000, "2020-03-22", 5, "active",    8),
    ("Agilent Signal Generator",   "Lab Equipment","ECE", "Electronics Lab, Block B",85000, "2019-07-14", 5, "under_repair",5),
    ("Digital Multimeter (x10)",   "Lab Equipment","ECE", "Electronics Lab, Block B",3500,  "2021-02-11", 3, "active",    7),
    ("Raspberry Pi 4 Kit (x20)",   "Computer",     "ECE", "Embedded Systems Lab, B", 9000,  "2022-11-05", 3, "active",    9),
    ("EPSON EB-W06 Projector",     "Projector",    "ECE", "ECE Seminar Hall",    26000,  "2021-04-19", 3, "active",    8),
    ("Soldering Station (x5)",     "Lab Equipment","ECE", "Electronics Lab, Block B",7000,  "2020-08-30", 5, "active",    6),
    ("Function Generator (x3)",    "Lab Equipment","ECE", "Electronics Lab, Block B",22000, "2019-12-01", 5, "damaged",   4),
    ("Wireless Router (TP-Link)",   "Networking",   "ECE", "ECE Faculty Block",   4500,   "2023-01-14", 3, "active",    9),

    # Mechanical
    ("Lathe Machine (HMT)",        "Lab Equipment","MECH","Workshop, Block C",   250000, "2016-05-10", 10,"active",    5),
    ("Bench Drilling Machine",     "Lab Equipment","MECH","Workshop, Block C",   35000,  "2018-09-20", 10,"active",    6),
    ("Vernier Caliper (x8)",       "Lab Equipment","MECH","Materials Lab, Block C",1200,  "2020-04-05", 5, "active",    8),
    ("Milling Machine",            "Lab Equipment","MECH","Workshop, Block C",   180000, "2015-11-15", 10,"under_repair",4),
    ("Hydraulic Press 10T",        "Lab Equipment","MECH","Fluids Lab, Block C",  95000, "2017-03-22", 10,"active",    6),
    ("AutoCAD Workstation (x4)",   "Computer",     "MECH","CAD Lab, Block C",    55000,  "2022-07-18", 3, "active",    9),
    ("Overhead Projector (old)",   "Projector",    "MECH","Lecture Hall M1",     12000,  "2015-02-28", 3, "retired",   2),
    ("Steel Almira (x4)",          "Furniture",    "MECH","Workshop, Block C",   6000,   "2018-01-10", 10,"active",    6),

    # Civil
    ("Total Station (Leica)",      "Lab Equipment","CIVIL","Survey Lab, Block D", 180000, "2019-06-14", 7, "active",    8),
    ("Theodolite (Sokkia)",        "Lab Equipment","CIVIL","Survey Lab, Block D", 85000,  "2018-11-20", 7, "active",    7),
    ("Compression Testing Machine","Lab Equipment","CIVIL","Concrete Lab, Block D",120000,"2017-08-12", 10,"active",    7),
    ("AutoCAD Civil Workstation",  "Computer",     "CIVIL","CAD Lab, Block D",   52000,  "2021-09-30", 3, "active",    8),
    ("Measuring Tape Set (x6)",    "Lab Equipment","CIVIL","Survey Lab, Block D", 800,    "2022-03-10", 3, "active",    9),
    ("HP DesignJet Plotter",       "Other",        "CIVIL","Drawing Room, Block D",75000, "2020-04-15", 5, "under_repair",5),
    ("Projector (Panasonic PT)",   "Projector",    "CIVIL","Civil Seminar Hall",  24000,  "2021-01-20", 3, "active",    8),

    # Library
    ("RFID Book Management System","Networking",   "LIB", "Main Library, Ground Floor",150000,"2021-08-01",5,"active",  9),
    ("HP All-in-One Desktop (x3)", "Computer",     "LIB", "Library Catalog Counter",   42000, "2020-05-15",3,"active",  7),
    ("Barcode Scanner (x4)",       "Other",        "LIB", "Book Issuing Counter",      3500,  "2021-06-10",3,"active",  8),
    ("Library Bookshelf (x20)",    "Furniture",    "LIB", "Main Library Stacks",       4500,  "2015-01-01",15,"active", 5),
    ("Photocopier (Ricoh MP2014)", "Other",        "LIB", "Library Copy Room",         58000, "2020-09-10",5,"damaged", 3),
    ("Reading Room Chairs (x50)",  "Furniture",    "LIB", "Reading Hall",              800,   "2017-06-01",10,"active", 5),

    # Admin / BBA
    ("Conference Table (12-seater)","Furniture",   "ADMIN","Conference Room 1",   85000,  "2019-03-15", 10,"active",   7),
    ("Presentation Screen 120\"",  "Other",        "ADMIN","Boardroom, Admin Block",35000, "2020-07-20", 7, "active",   8),
    ("HP Color LaserJet (x2)",     "Other",        "ADMIN","Admin Office",        38000,  "2021-11-05", 3, "active",   8),
    ("CCTV System (32 cameras)",   "Networking",   "ADMIN","Campus-wide",        120000,  "2022-01-10", 5, "active",   9),
    ("AC Split Unit (x8)",         "HVAC",         "ADMIN","Admin Block",         45000,  "2020-06-01", 10,"under_repair",5),
    ("Dell Vostro Admin Laptop",   "Computer",     "ADMIN","Principal's Office",  55000,  "2023-04-15", 3, "active",   9),
]

def seed():
    with app.app_context():
        print("🌱 Dropping and recreating all tables…")
        db.drop_all()
        db.create_all()

        # ── Departments ───────────────────────────────────────────
        print("📦 Seeding departments…")
        depts = {}
        for d in DEPARTMENTS:
            dept = Department(**d)
            db.session.add(dept)
            depts[d["code"]] = dept
        db.session.commit()

        # ── Users ─────────────────────────────────────────────────
        print("👥 Seeding users…")
        admin = User(username="admin", email="admin@assetpulse.ac.in",
                     full_name="System Administrator", role="admin", is_active=True)
        admin.set_password("admin123")

        cse_staff = User(username="cse_staff", email="cse@assetpulse.ac.in",
                         full_name="Vijay Krishnamurthy", role="department",
                         department_id=None, is_active=True)
        cse_staff.set_password("staff123")

        ece_staff = User(username="ece_staff", email="ece@assetpulse.ac.in",
                         full_name="Lakshmi Menon", role="department", is_active=True)
        ece_staff.set_password("staff123")

        maint1 = User(username="maint1", email="maint1@assetpulse.ac.in",
                      full_name="Rajan Pillai", role="maintenance", is_active=True)
        maint1.set_password("maint123")

        maint2 = User(username="maint2", email="maint2@assetpulse.ac.in",
                      full_name="Sanjay Verma", role="maintenance", is_active=True)
        maint2.set_password("maint123")

        lib_staff = User(username="lib_staff", email="lib@assetpulse.ac.in",
                         full_name="Sunitha Rajan", role="department", is_active=True)
        lib_staff.set_password("staff123")

        all_users = [admin, cse_staff, ece_staff, maint1, maint2, lib_staff]
        for u in all_users:
            db.session.add(u)
        db.session.flush()

        # Link dept staff to departments
        cse_staff.department_id = depts["CSE"].id
        ece_staff.department_id = depts["ECE"].id
        lib_staff.department_id = depts["LIB"].id
        db.session.commit()

        # ── Assets ────────────────────────────────────────────────
        print("🗃️  Seeding 46 assets…")
        created_assets = []
        tag_counters = {code: 0 for code in depts}

        for (name, category, dept_code, location, cost, pd_str, warranty_yrs, status, condition) in ASSETS_SEED:
            tag_counters[dept_code] += 1
            dept = depts[dept_code]
            pd = date.fromisoformat(pd_str)
            we = date(pd.year + warranty_yrs, pd.month, pd.day)

            asset = Asset(
                asset_tag=f"{dept_code}-{tag_counters[dept_code]:03d}",
                name=name,
                category=category,
                department_id=dept.id,
                location=location,
                purchase_date=pd,
                purchase_cost=cost,
                warranty_expiry=we,
                status=status,
                condition_rating=condition,
                manufacturer={
                    "Computer": "Dell", "Projector": "Epson",
                    "Lab Equipment": "Agilent", "Networking": "Cisco",
                    "Furniture": "Godrej", "Other": "HP", "HVAC": "Daikin",
                    "Electrical": "APC", "Vehicle": "Toyota"
                }.get(category, "Generic"),
            )
            db.session.add(asset)
            created_assets.append((asset, dept_code))

        db.session.flush()

        # ── Maintenance Logs ──────────────────────────────────────
        print("🔧 Seeding maintenance logs…")
        maint_data = [
            # (asset_index, issue, status, priority, days_ago_request, days_ago_complete, est_cost, actual_cost, tech_notes)
            (3,  "Monitor display flickering on startup",          "in_progress","high",    20, None, 2500,  0,     None),
            (5,  "Projector bulb blown, image very dim",           "pending",    "critical", 5, None, 12000, 0,     None),
            (10, "Oscilloscope probe set damaged",                  "resolved",   "medium",  90, 60,   3000,  2800,  "Replaced probes. Calibration done."),
            (11, "Signal generator power supply failure",           "in_progress","high",    15, None, 8000,  0,     None),
            (21, "Milling machine spindle vibration issue",         "pending",    "critical",  3, None, 25000, 0,     None),
            (28, "Total station tripod leg cracked",                "resolved",   "medium",  180,150, 5000,  4500,  "Replaced tripod. Re-aligned optics."),
            (37, "Photocopier paper jam, fuser unit damaged",       "pending",    "high",    10, None, 7500,  0,     None),
            (43, "AC unit not cooling — refrigerant leak",          "in_progress","high",    8,  None, 6000,  0,     None),
            (5,  "Previous projector issue — lamp replaced",        "resolved",   "high",   365, 340, 15000, 14200, "Lamp replaced. Projector operational."),
            (10, "Oscilloscope calibration scheduled service",      "resolved",   "low",    400, 380, 2000,  1800,  "Annual calibration completed."),
            (3,  "Monitor backlight issue",                         "resolved",   "medium", 300, 275, 3500,  3200,  "Backlight replaced. All monitors OK."),
            (21, "Milling machine belt replacement",                "resolved",   "high",   500, 480, 8000,  7500,  "Drive belt replaced. Machine running."),
        ]

        for (idx, issue, status, priority, days_req, days_done, est_cost, act_cost, notes) in maint_data:
            if idx - 1 >= len(created_assets):
                continue
            asset_obj = created_assets[idx - 1][0]
            req_date  = date.today() - timedelta(days=days_req)
            comp_date = date.today() - timedelta(days=days_done) if days_done else None
            sched_date= req_date + timedelta(days=random.randint(3, 14))

            log = MaintenanceLog(
                asset_id=asset_obj.id,
                requested_by_id=cse_staff.id,
                assigned_to_id=maint1.id if status in ("in_progress", "resolved") else None,
                request_date=req_date,
                scheduled_date=sched_date,
                completed_date=comp_date,
                status=status,
                priority=priority,
                issue_description=issue,
                technician_notes=notes,
                estimated_cost=est_cost,
                actual_cost=act_cost,
                next_due_date=(comp_date + timedelta(days=365)) if comp_date else None,
            )
            db.session.add(log)

        db.session.commit()

        # ── Allocation History ────────────────────────────────────
        print("🔄 Seeding allocation history…")
        for i in range(5):
            asset_obj = created_assets[i * 3][0]
            alloc = AllocationHistory(
                asset_id=asset_obj.id,
                from_department_id=depts["CSE"].id,
                to_department_id=depts["ECE"].id,
                allocated_by_id=admin.id,
                allocation_date=date.today() - timedelta(days=random.randint(30, 300)),
                reason="Temporary allocation for joint lab project",
            )
            db.session.add(alloc)
        db.session.commit()

        # ── Budget Estimates ──────────────────────────────────────
        print("💰 Seeding budget estimates…")
        from app.utils.cost_estimator import estimated_maintenance_cost, estimated_replacement_cost
        from sqlalchemy import func

        current_year = date.today().year
        for dept_code, dept in depts.items():
            assets_in_dept = Asset.query.filter_by(department_id=dept.id, status__in=["active","under_repair","damaged"]).all() if False else \
                             Asset.query.filter(Asset.department_id == dept.id, Asset.status != "retired").all()
            total_maint = sum(estimated_maintenance_cost(a) for a in assets_in_dept)
            total_repl  = sum(estimated_replacement_cost(a) for a in assets_in_dept)

            actual = (
                db.session.query(func.sum(MaintenanceLog.actual_cost))
                .join(Asset)
                .filter(Asset.department_id == dept.id, MaintenanceLog.status == "resolved")
                .scalar() or 0
            )

            est = BudgetEstimate(
                department_id=dept.id,
                fiscal_year=current_year,
                category="All",
                estimated_maintenance_cost=total_maint,
                estimated_replacement_cost=total_repl,
                actual_spent=float(actual),
                prepared_by_id=admin.id,
            )
            db.session.add(est)

        db.session.commit()

        # ── Activity Logs ─────────────────────────────────────────
        print("📝 Seeding activity logs…")
        sample_actions = [
            ("LOGIN",  "User",  admin.id,  "admin logged in"),
            ("CREATE", "Asset", 1,         "Created asset CSE-001"),
            ("UPDATE", "Asset", 5,         "Updated status to under_repair"),
            ("CREATE", "MaintenanceLog", 1,"Maintenance request for CSE-006"),
            ("LOGIN",  "User",  cse_staff.id, "cse_staff logged in"),
        ]
        for action, entity_type, entity_id, desc in sample_actions:
            log = ActivityLog(
                user_id=admin.id,
                action=action, entity_type=entity_type,
                entity_id=entity_id, description=desc,
                ip_address="127.0.0.1",
            )
            db.session.add(log)

        db.session.commit()

        print("\n✅ Seeding complete!")
        print(f"   Departments : {Department.query.count()}")
        print(f"   Users       : {User.query.count()}")
        print(f"   Assets      : {Asset.query.count()}")
        print(f"   Maint. Logs : {MaintenanceLog.query.count()}")
        print(f"   Budgets     : {BudgetEstimate.query.count()}")
        print("\n🔑 Login Credentials:")
        print("   Admin:       admin / admin123")
        print("   CSE Staff:   cse_staff / staff123")
        print("   Maintenance: maint1 / maint123")


if __name__ == "__main__":
    seed()
