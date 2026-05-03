import csv
from pathlib import Path

from flask import current_app

from extensions import db
from models.attendance_model import Attendance
from models.user_model import User


ATTENDANCE_HEADERS = [
    'record_id',
    'student_id',
    'student_name',
    'email',
    'subject',
    'status',
    'approval_status',
    'remarks',
    'date',
    'approved_by',
    'approved_at',
]


def attendance_sheet_path():
    return Path(current_app.config['ATTENDANCE_SHEET_FILE'])


def _fmt_date(value):
    if not value:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return str(value)


def ensure_attendance_sheet():
    path = attendance_sheet_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=ATTENDANCE_HEADERS)
            writer.writeheader()


def sync_attendance_sheet():
    path = attendance_sheet_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = (
        db.session.query(Attendance, User)
        .outerjoin(User, Attendance.user_id == User.id)
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .all()
    )

    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=ATTENDANCE_HEADERS)
        writer.writeheader()
        for attendance, student in rows:
            approved_by_user = db.session.get(User, attendance.approved_by) if attendance.approved_by else None
            writer.writerow({
                'record_id': attendance.id,
                'student_id': student.student_id if student else '',
                'student_name': student.name if student else '',
                'email': student.email if student else '',
                'subject': attendance.subject or '',
                'status': attendance.status or '',
                'approval_status': attendance.approval_status or '',
                'remarks': attendance.remarks or '',
                'date': _fmt_date(attendance.date),
                'approved_by': approved_by_user.name if approved_by_user else '',
                'approved_at': _fmt_date(attendance.approved_at),
            })
