import os
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))        # backend/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..")) # project root
FRONTEND_STATIC = os.path.join(PROJECT_ROOT, "frontend", "static")


def resolve_db_uri(raw_url: str, base_dir: str) -> str:
    """
    Validates and resolves the database URI.
    If a remote MySQL or PostgreSQL host is unreachable or DNS resolution fails
    (e.g. Aiven cloud service paused/expired), it automatically and gracefully
    falls back to the local SQLite database to prevent downtime.
    """
    sqlite_fallback = f"sqlite:///{os.path.join(base_dir, 'assetpulse.db')}"
    if not raw_url:
        return sqlite_fallback

    url = raw_url.strip()
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Test remote host connectivity for MySQL / Postgres
    if "mysql" in url or "postgresql" in url:
        parsed = None
        try:
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (3306 if "mysql" in url else 5432)
            if host and host not in ("localhost", "127.0.0.1"):
                socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except Exception as e:
            host_label = getattr(parsed, "hostname", "remote host") if parsed else "remote host"
            print(f"[WARNING] Remote database host '{host_label}' unreachable ({e}).")
            print(f"[INFO] Automatically falling back to local SQLite: {sqlite_fallback}")
            return sqlite_fallback

    if url.startswith("sqlite:///") and not os.path.isabs(url[10:]):
        url = f"sqlite:///{os.path.join(base_dir, url[10:])}"

    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # Upload / QR paths — point to frontend/static/ folder
    UPLOAD_FOLDER = os.path.join(FRONTEND_STATIC, "uploads")
    QR_FOLDER = os.path.join(FRONTEND_STATIC, "qrcodes")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "AssetPulse <noreply@assetpulse.com>")

    # WTF
    WTF_CSRF_ENABLED = True


class DevelopmentConfig(Config):
    DEBUG = True
    _db_url = resolve_db_uri(os.environ.get("DATABASE_URL"), BASE_DIR)
    SQLALCHEMY_DATABASE_URI = _db_url

    # Auto-enable SSL connect_args for MySQL connections (e.g. Aiven Cloud)
    _dev_engine_opts = dict(Config.SQLALCHEMY_ENGINE_OPTIONS)
    if _db_url and "mysql" in _db_url:
        _dev_engine_opts["connect_args"] = {"ssl": {}}
    SQLALCHEMY_ENGINE_OPTIONS = _dev_engine_opts


class ProductionConfig(Config):
    DEBUG = False
    _db_url = resolve_db_uri(os.environ.get("DATABASE_URL"), BASE_DIR)
    SQLALCHEMY_DATABASE_URI = _db_url
    WTF_CSRF_ENABLED = False

    _prod_engine_opts = dict(Config.SQLALCHEMY_ENGINE_OPTIONS)
    if _db_url and "mysql" in _db_url:
        _prod_engine_opts["connect_args"] = {"ssl": {}}
    SQLALCHEMY_ENGINE_OPTIONS = _prod_engine_opts


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
