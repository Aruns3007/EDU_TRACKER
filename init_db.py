from app import app, db


with app.app_context():
    print("Resetting database tables...")
    db.drop_all()
    db.create_all()
    print("Database is now synced with your model!")
