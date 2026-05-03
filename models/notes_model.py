from extensions import db
from datetime import datetime

class Notes(db.Model):
    # Unique ID for each note
    id = db.Column(db.Integer, primary_key=True)
    
    # Information about the file
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    
    # Metadata
    date_uploaded = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship: Connects the note to the student who uploaded it
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Note {self.title}>'