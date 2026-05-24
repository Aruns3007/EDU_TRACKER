import os
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from models.attendance_model import Attendancefrom models.notes_model import Notes
from models.homework_model import Homework
from models.timetable_model import Timetable
from models.teacher_notes_model import TeacherNote
from models.user_model import User
from extensions import db
from datetime import datetime
from werkzeug.utils import secure_filename
from routes.access_control import student_required
from services.subject_utils import normalize_subject, any_subject_match_clause

dash = Blueprint('dash', __name__)

@dash.route('/dashboard', methods=['GET', 'POST'])
@student_required
def dashboard():
    # 1. Calculate Attendance Percentage (Eligibility Ring)
    approved_logs = Attendance.query.filter_by(user_id=current_user.id, approval_status='Approved').count()
    present_logs = Attendance.query.filter_by(
        user_id=current_user.id,
        status='Present',
        approval_status='Approved'
    ).count()
    pending_logs = Attendance.query.filter_by(user_id=current_user.id, approval_status='Pending').count()
    
    attendance_rate = (present_logs / approved_logs * 100) if approved_logs > 0 else 0
    
    # 2. Bunk Manager (75% Criteria)
    # Tells student how many more classes they can skip without falling below 75%
    if attendance_rate >= 75:
        safe_bunks = int((present_logs / 0.75) - approved_logs)
    else:
        safe_bunks = 0

    # 3. Exam Readiness (Based on Notes Vault)
    notes_count = Notes.query.filter_by(user_id=current_user.id).count()
    if notes_count == 0:
        readiness = "Low"
        color = "#ef4444" # Red
    elif notes_count < 5:
        readiness = "Medium"
        color = "#f59e0b" # Orange
    else:
        readiness = "High"
        color = "#10b981" # Green

    # 4. Get Today's Schedule
    today = datetime.now().strftime('%A')
    schedule = Timetable.query.filter_by(user_id=current_user.id, day=today).all()

    # 5. DYNAMIC SUBJECTS FOR QUICK LOG (The Fix)
    # We query all unique subject names from the student's timetable
    subject_query = db.session.query(Timetable.subject).filter_by(user_id=current_user.id).distinct().all()
    # Convert list of tuples like [('Python',), ('Math',)] into a clean list ['Python', 'Math']
    dynamic_subjects = [normalize_subject(s[0]) for s in subject_query if normalize_subject(s[0])]

    # Default subjects if their timetable is empty
    if not dynamic_subjects:
        dynamic_subjects = ["General Studies", "Project Work"]

    teacher_notes = (
        TeacherNote.query
        .filter(any_subject_match_clause(TeacherNote.subject, dynamic_subjects))
        .order_by(TeacherNote.created_at.desc())
        .limit(6)
        .all()
    )
    teacher_notes_count = TeacherNote.query.filter(any_subject_match_clause(TeacherNote.subject, dynamic_subjects)).count()

    # 6. Get Upcoming Homework
    homework_items = Homework.query.order_by(
        Homework.due_date.is_(None),  # Homework without due date appears last
        Homework.due_date.asc(),      # Upcoming due dates first
        Homework.created_at.desc()    # Newest created first for same due date
    ).all()

    if request.method == 'POST':
        new_name = request.form.get('name', '').strip()
        new_email = request.form.get('email', '').strip().lower()
        new_phone = request.form.get('phone_number', '').strip()
        new_parent_name = request.form.get('parent_name', '').strip()
        new_parent_phone = request.form.get('parent_phone', '').strip()
        new_parent_email = request.form.get('parent_email', '').strip().lower()
        new_address = request.form.get('address', '').strip()

        if new_email and new_email != current_user.email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user and existing_user.id != current_user.id:
                flash('That email is already in use by another account.', 'danger')
                return redirect(url_for('dash.dashboard'))

        current_user.name = new_name or current_user.name
        current_user.email = new_email or current_user.email
        current_user.phone_number = new_phone or None
        current_user.parent_name = new_parent_name or None
        current_user.parent_phone = new_parent_phone or None
        current_user.parent_email = new_parent_email or None
        current_user.address = new_address or None

        profile_file = request.files.get('profile_image')
        if profile_file and profile_file.filename:
            filename = secure_filename(f"profile_u{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{profile_file.filename}")
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'profile_images')
            os.makedirs(upload_dir, exist_ok=True)
            file_path = os.path.join(upload_dir, filename)
            profile_file.save(file_path)
            current_user.profile_image = f"uploads/profile_images/{filename}"

        try:
            db.session.commit()
            flash('Profile updated successfully.', 'success')
        except Exception as exc:
            db.session.rollback()
            flash('Could not update your profile right now.', 'danger')
            print(f"Profile update error: {exc}")

        return redirect(url_for('dash.dashboard'))

    return render_template('dashboard.html', 
                           attendance=round(attendance_rate, 1),
                           safe_bunks=max(0, safe_bunks), # Ensures it never shows negative
                           readiness=readiness,
                           readiness_color=color,
                           notes_count=notes_count,
                           teacher_notes=teacher_notes,
                           teacher_notes_count=teacher_notes_count,
                           schedule=schedule,
                           today=today,
                           subjects=dynamic_subjects,
                           pending_logs=pending_logs, 
                           approved_logs=approved_logs,
                           homework_items=homework_items) # Pass homework items to the template
