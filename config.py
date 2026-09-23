import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))        # backend/
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..")) # project root
FRONTEND_STATIC = os.path.join(PROJECT_ROOT, "frontend", "static")


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
    _db_url = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'assetpulse.db')}",
    )
    # If a bare relative sqlite URL is given (e.g. sqlite:///assetpulse.db),
    # resolve it to an absolute path inside BASE_DIR so it always finds the db.
    if _db_url and _db_url.startswith("sqlite:///") and not os.path.isabs(_db_url[10:]):
        _db_url = f"sqlite:///{os.path.join(BASE_DIR, _db_url[10:])}"
    SQLALCHEMY_DATABASE_URI = _db_url


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    WTF_CSRF_ENABLED = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
