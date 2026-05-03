from extensions import db

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    day = db.Column(db.String(20), nullable=False) # e.g., 'Monday'
    start_time = db.Column(db.String(10), nullable=False) # e.g., '09:00'
    end_time = db.Column(db.String(10), nullable=False) # e.g., '10:00'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(20), default='college', nullable=False)

    def __repr__(self):
        return f'<Timetable {self.subject} on {self.day}>'
