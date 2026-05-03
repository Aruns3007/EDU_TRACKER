from app import app, db

from models.attendance_model import Attendance
from models.homework_model import Homework
from models.notes_model import Notes
from models.timetable_model import Timetable
from models.user_model import User
from models.vault_model import StudentDocs


with app.app_context():
    print('Creating database...')
    db.create_all()
    print('Success! database tables are ready.')
