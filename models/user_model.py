from extensions import db  # <--- Change this
from flask_login import UserMixin

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    student_id = db.Column(db.String(20))
    role = db.Column(db.String(20), default='student', nullable=False)
    subject = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    parent_name = db.Column(db.String(100))
    parent_phone = db.Column(db.String(20))
    parent_email = db.Column(db.String(100))
    address = db.Column(db.String(255))
    profile_image = db.Column(db.String(255))

    @property
    def username(self):
        return self.name or self.email

    @property
    def is_teacher(self):
        return (self.role or 'student') == 'teacher'

    @property
    def is_student(self):
        return (self.role or 'student') == 'student'
