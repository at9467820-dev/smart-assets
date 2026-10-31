"""
Migrate all data from local SQLite database (assetpulse.db) to Aiven MySQL.
"""
import os
import sys
import sqlite3
import urllib.parse
from datetime import datetime, date
from decimal import Decimal
from dotenv import load_dotenv
from sqlalchemy import text, inspect

load_dotenv()

# Read Aiven credentials from .env
host = os.getenv("Host")
port = os.getenv("Port", "25910")
user = os.getenv("User", "avnadmin")
password = os.getenv("Password")
database = os.getenv("Database name", "defaultdb")

if not host or not password:
    print("Error: Missing Host or Password in .env")
    sys.exit(1)

encoded_password = urllib.parse.quote_plus(password)
mysql_uri = f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{database}"

os.environ["DATABASE_URL"] = mysql_uri

from app import create_app
from app.extensions import db
from app.models import (
    Department,
    User,
    Asset,
    MaintenanceLog,
    AssetIssue,
    AssetOrder,
    AllocationHistory,
    BudgetEstimate,
    ActivityLog,
)

app = create_app("development")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "connect_args": {"ssl": {}},
}

sqlite_path = os.path.join(os.path.dirname(__file__), "assetpulse.db")
if not os.path.exists(sqlite_path):
    print(f"Error: SQLite database not found at {sqlite_path}")
    sys.exit(1)

def parse_date(val):
    if val is None or val == "":
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    val_str = str(val).strip().split(" ")[0].split("T")[0]
    return date.fromisoformat(val_str)

def parse_datetime(val):
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    val_str = str(val).strip()
    # Handle formats like '2026-10-08 10:12:00.332916'
    try:
        return datetime.fromisoformat(val_str)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                pass
    return val

def migrate_data():
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    models_in_order = [
        Department,
        User,
        Asset,
        AssetOrder,
        BudgetEstimate,
        MaintenanceLog,
        AssetIssue,
        AllocationHistory,
        ActivityLog,
    ]

    with app.app_context():
        # Ensure schema is up-to-date
        print("1. Ensuring all MySQL tables exist...")
        db.create_all()

        print("2. Disabling foreign key checks on MySQL for clean migration...")
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))

        # Truncate / clean tables in MySQL before migrating to avoid duplicates
        print("3. Clearing existing MySQL tables...")
        for model in reversed(models_in_order):
            table_name = model.__tablename__
            db.session.execute(text(f"TRUNCATE TABLE `{table_name}`;"))
        db.session.commit()

        print("4. Migrating records from SQLite to MySQL...")
        total_migrated = 0

        for model in models_in_order:
            table_name = model.__tablename__
            table = model.__table__
            cols = {col.name: col for col in table.columns}

            sqlite_cur.execute(f"SELECT * FROM `{table_name}`")
            rows = sqlite_cur.fetchall()
            print(f"\nMigrating `{table_name}` ({len(rows)} records)...")

            records_to_insert = []
            for row in rows:
                record = {}
                row_dict = dict(row)
                for col_name, val in row_dict.items():
                    if col_name not in cols:
                        continue
                    col_type = cols[col_name].type

                    # Convert SQLite types to appropriate Python/MySQL types
                    if val is None:
                        record[col_name] = None
                    elif hasattr(col_type, "python_type"):
                        py_type = col_type.python_type
                        if py_type is date:
                            record[col_name] = parse_date(val)
                        elif py_type is datetime:
                            record[col_name] = parse_datetime(val)
                        elif py_type is bool:
                            record[col_name] = bool(val)
                        elif py_type is Decimal or py_type is float:
                            record[col_name] = Decimal(str(val))
                        elif py_type is int:
                            record[col_name] = int(val)
                        else:
                            record[col_name] = str(val) if val is not None else None
                    else:
                        record[col_name] = val
                records_to_insert.append(record)

            if records_to_insert:
                db.session.execute(table.insert(), records_to_insert)
                db.session.commit()
                print(f"  -> Successfully inserted {len(records_to_insert)} records into `{table_name}`")
                total_migrated += len(records_to_insert)
            else:
                print(f"  -> Table `{table_name}` has 0 records.")

        print("\n5. Re-enabling foreign key checks on MySQL...")
        db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        db.session.commit()

        print("\n6. Verifying row counts...")
        all_matched = True
        print(f"{'Table':<22} | {'SQLite Count':<12} | {'MySQL Count':<12} | {'Status'}")
        print("-" * 60)
        for model in models_in_order:
            table_name = model.__tablename__
            sqlite_cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            s_count = sqlite_cur.fetchone()[0]
            m_count = db.session.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()
            status = "MATCH" if s_count == m_count else "MISMATCH"
            if s_count != m_count:
                all_matched = False
            print(f"{table_name:<22} | {s_count:<12} | {m_count:<12} | {status}")

        print("-" * 60)
        if all_matched:
            print(f"SUCCESS: All {total_migrated} records successfully migrated and verified!")
        else:
            print("WARNING: Some row counts did not match.")

    sqlite_conn.close()

if __name__ == "__main__":
    migrate_data()

