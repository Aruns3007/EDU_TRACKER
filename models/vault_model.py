from extensions import db
from datetime import datetime

class StudentDocs(db.Model):
    __tablename__ = 'student_docs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    doc_type = db.Column(db.String(100), default='Other Certificate')
    upload_date = db.Column(db.String(20), default=datetime.now().strftime('%Y-%m-%d'))

    def __repr__(self):
        return f'<Document {self.file_name}>'