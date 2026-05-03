from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from models.attendance_model import Attendance
from extensions import db
from datetime import datetime
from routes.access_control import student_required
from services.attendance_sheet import sync_attendance_sheet
from services.subject_utils import normalize_subject, subject_match_clause

# 1. Define the Blueprint
att = Blueprint('att', __name__)

# 2. View Attendance Page
@att.route('/attendance')
@student_required
def attendance_view():
    """Renders the high-tech attendance log page."""
    # Fetch all logs for the current student, newest first
    logs = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.date.desc(), Attendance.id.desc()).all()
    
    # Passing 'now' so the UI can show the current system time
    return render_template('attendance.html', logs=logs, now=datetime.now())

# 3. Mark Attendance Logic
@att.route('/mark', methods=['POST'])
@student_required
def mark_attendance():
    """Handles the form submission from the dashboard."""
    subject = normalize_subject(request.form.get('subject'))
    status = request.form.get('status')
    today = datetime.now().date()
    
    if not subject or not status:
        flash('Selection error: Subject and Status are required.', 'danger')
        return redirect(url_for('dash.dashboard'))

    # Optional: Prevent double-marking same subject on same day
    existing = Attendance.query.filter_by(
        user_id=current_user.id, 
        date=today 
    ).filter(subject_match_clause(Attendance.subject, subject)).first()

    if existing:
        if existing.approval_status == 'Rejected':
            existing.status = status
            existing.approval_status = 'Pending'
            existing.approved_by = None
            existing.approved_at = None
            db.session.commit()
            sync_attendance_sheet()
            flash(f'{subject} attendance resubmitted for approval.', 'success')
        else:
            flash(f'Already submitted {subject} for today. Waiting for teacher approval.', 'info')
    else:
        new_log = Attendance(
            user_id=current_user.id,
            subject=subject,
            status=status,
            date=today,  # Ensures the date is explicitly set to today
            approval_status='Pending'
        )
        db.session.add(new_log)
        db.session.commit()
        sync_attendance_sheet()
        flash(f'{subject} submitted and is now waiting for teacher approval.', 'success')
    
    return redirect(url_for('att.attendance_view')) # Redirect to the log instead of dashboard
