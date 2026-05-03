from app import app, db
from config import INSTANCE_PATH

# This script wipes the configured DB file and recreates schema.
with app.app_context():
    print("Resetting database...")
    db.session.remove()
    db.engine.dispose()
    db.create_all()
    print("Database recreated successfully!")
