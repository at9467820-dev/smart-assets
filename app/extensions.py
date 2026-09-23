from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
mail = Mail()

login_manager.login_view = "auth.register"
login_manager.login_message = "Please register an account or sign in to access AssetPulse."
login_manager.login_message_category = "info"
