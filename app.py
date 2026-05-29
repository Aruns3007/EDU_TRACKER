from flask import Flask, render_template
from extensions import db, bcrypt, login_manager
from config import Config, INSTANCE_PATH
import os
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.config.from_object(Config)

# --- 2. Initialize Extensions ---
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)

# --- 3. Login Manager Setup ---
from models.user_model import User

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# --- 4. Import Models ---
from models.attendance_model import Attendance
from models.notes_model import Notes
from models.timetable_model import Timetable
from models.vault_model import StudentDocs 
from models.homework_model import Homework
from models.teacher_notes_model import TeacherNote
from services.attendance_sheet import ensure_attendance_sheet

# --- 5. Register Blueprints ---
from routes.auth_routes import auth
from routes.dashboard_routes import dash
from routes.ai_routes import ai
from routes.notes_routes import learning
from routes.attendance_routes import att
from routes.timetable_routes import time_table 
from routes.teacher_routes import teacher
from routes.admin_routes import admin
from routes.reminder_routes import reminders

app.register_blueprint(auth)
app.register_blueprint(dash)
app.register_blueprint(ai)
app.register_blueprint(learning)
app.register_blueprint(att)
app.register_blueprint(time_table) 
app.register_blueprint(teacher)
app.register_blueprint(admin)
app.register_blueprint(reminders)

# --- 6. Home Route ---
@app.route('/')
def index():
    return render_template('index.html')

# --- 7. System Initialization ---
def setup_folders():
    """Ensures necessary directories exist before the app starts."""
    folders = [
        INSTANCE_PATH,
        app.config.get('UPLOAD_FOLDER', 'uploads'),
        Path(app.config.get('UPLOAD_FOLDER', 'uploads')) / 'teacher_notes',
        Path(app.config.get('UPLOAD_FOLDER', 'uploads')) / 'profile_images',
        app.config.get('VAULT_FOLDER', 'vault'),
        Path(app.config.get('ATTENDANCE_SHEET_FILE', 'instance/attendance_records.csv')).parent,
    ]
    for folder in folders:
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            print(f">>> Initialized folder: {folder}")

def init_db():
    """Creates database tables."""
    with app.app_context():
        db.create_all()
        ensure_user_roles()
        ensure_teacher_subject_column()
        ensure_student_profile_columns()
        ensure_teacher_notes_columns()
        ensure_attendance_columns()
        ensure_attendance_sheet()
        print(">>> Database tables verified/created.")

def ensure_user_roles():
    """Adds teacher role support to older SQLite databases."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if not db_path:
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cur.fetchall()]
        if 'role' not in columns:
            cur.execute("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'student'")
        cur.execute("UPDATE user SET role='student' WHERE role IS NULL OR role = ''")
        conn.commit()
    except Exception as exc:
        print(f">>> SQLite schema check skipped: {exc}")
    finally:
        if conn is not None:
            conn.close()

def ensure_teacher_subject_column():
    """Adds teacher subject support to older SQLite databases."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if not db_path:
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cur.fetchall()]
        if 'subject' not in columns:
            cur.execute("ALTER TABLE user ADD COLUMN subject VARCHAR(100)")
        cur.execute("UPDATE user SET subject='General Studies' WHERE role='teacher' AND (subject IS NULL OR subject = '')")
        conn.commit()
    except Exception as exc:
        print(f">>> Teacher subject schema check skipped: {exc}")
    finally:
        if conn is not None:
            conn.close()

def ensure_student_profile_columns():
    """Adds student profile fields to older SQLite databases."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if not db_path:
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(user)")
        columns = [row[1] for row in cur.fetchall()]
        schema_updates = {
            'phone_number': "ALTER TABLE user ADD COLUMN phone_number VARCHAR(20)",
            'parent_name': "ALTER TABLE user ADD COLUMN parent_name VARCHAR(100)",
            'parent_phone': "ALTER TABLE user ADD COLUMN parent_phone VARCHAR(20)",
            'parent_email': "ALTER TABLE user ADD COLUMN parent_email VARCHAR(100)",
            'address': "ALTER TABLE user ADD COLUMN address VARCHAR(255)",
            'profile_image': "ALTER TABLE user ADD COLUMN profile_image VARCHAR(255)",
        }
        for column_name, statement in schema_updates.items():
            if column_name not in columns:
                cur.execute(statement)
        conn.commit()
    except Exception as exc:
        print(f">>> Student profile schema check skipped: {exc}")
    finally:
        if conn is not None:
            conn.close()

def ensure_teacher_notes_columns():
    """Adds attachment support for teacher notes to older SQLite databases."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if not db_path:
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(teacher_note)")
        columns = [row[1] for row in cur.fetchall()]
        if 'content' not in columns:
            cur.execute("ALTER TABLE teacher_note ADD COLUMN content TEXT")
        if 'attachment_name' not in columns:
            cur.execute("ALTER TABLE teacher_note ADD COLUMN attachment_name VARCHAR(255)")
        if 'attachment_path' not in columns:
            cur.execute("ALTER TABLE teacher_note ADD COLUMN attachment_path VARCHAR(500)")
        conn.commit()
    except Exception as exc:
        print(f">>> Teacher note schema check skipped: {exc}")
    finally:
        if conn is not None:
            conn.close()

def ensure_attendance_columns():
    """Adds attendance approval columns for older SQLite databases."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return

    db_path = db_uri.replace('sqlite:///', '', 1)
    if not db_path:
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(attendance)")
        columns = [row[1] for row in cur.fetchall()]
        if 'approval_status' not in columns:
            cur.execute("ALTER TABLE attendance ADD COLUMN approval_status VARCHAR(20) DEFAULT 'Approved'")
        if 'approved_by' not in columns:
            cur.execute("ALTER TABLE attendance ADD COLUMN approved_by INTEGER")
        if 'approved_at' not in columns:
            cur.execute("ALTER TABLE attendance ADD COLUMN approved_at DATETIME")
        cur.execute("UPDATE attendance SET approval_status='Approved' WHERE approval_status IS NULL OR approval_status = ''")
        conn.commit()
    except Exception as exc:
        print(f">>> Attendance schema check skipped: {exc}")
    finally:
        if conn is not None:
            conn.close()

# --- 8. Execution ---
if __name__ == "__main__":
    # Ensure folders are ready first
    setup_folders()
    init_db()
    # Disable the reloader to avoid SQLite file-lock races on Windows.
    # Restart the server manually after code changes.
    app.run(debug=True, port=5000, use_reloader=False)
