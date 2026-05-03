from extensions import db  # <--- MUST BE extensions, NOT app
from datetime import datetime

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.String(100))
    status = db.Column(db.String(10)) 
    date = db.Column(db.Date, default=lambda: datetime.utcnow().date())
    remarks = db.Column(db.String(280))
    approval_status = db.Column(db.String(20), default='Pending', nullable=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)

    def __repr__(self):
        return f'<Attendance {self.subject} - {self.status}>'
