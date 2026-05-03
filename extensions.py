from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager

# Initialize the extensions without an app object yet.
# This "deferred initialization" allows for a cleaner modular structure.
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()