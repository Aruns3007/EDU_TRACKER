import csv
import io
import os
from datetime import datetime
from uuid import uuid4
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from extensions import bcrypt, db
from models.attendance_model import Attendance
from models.homework_model import Homework
from models.teacher_notes_model import TeacherNote
from models.user_model import User
from routes.access_control import teacher_required
from services.subject_utils import normalize_subject, subjects_match, subject_match_clause
teacher = Blueprint('teacher', __name__, url_prefix='/teacher')

SUBJECT_OPTIONS = [
    'Mathematics',
    'Physics',
    'Chemistry',
    'Biology',
    'Computer Science',
    'English',
    'Social Studies',
    'Tamil',
    'Hindi',
    'Economics',
    'Business Studies',
    'General Studies',
    'Other',
]


def _normalize_teacher_subject(raw_subject, custom_subject=''):
    subject = normalize_subject(custom_subject or raw_subject)
    if not subject:
        return 'General Studies'
    if subject.lower() == 'other':
        return 'General Studies'
    return subject


def _teacher_subject(user):
    subject = getattr(user, 'subject', None)
    normalized = normalize_subject(subject) if isinstance(subject, str) else ''
    return normalized if normalized else 'General Studies'


def _student_query():
    return User.query.filter(or_(User.role == 'student', User.role.is_(None)))


def _teacher_notes_folder():
    folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'teacher_notes')
    os.makedirs(folder, exist_ok=True)
    return folder


def _resolve_static_relative_path(relative_path):
    if not relative_path:
        return None

    static_root = Path(current_app.static_folder).resolve()
    candidate = (static_root / relative_path).resolve()
    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None
    return candidate


@teacher.route('/signup', methods=['GET', 'POST'])
def teacher_signup():
    if current_user.is_authenticated:
        if getattr(current_user, 'role', 'student') == 'admin':
            return redirect(url_for('admin.dashboard'))
        if getattr(current_user, 'role', 'student') == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('dash.dashboard'))

    if request.method == 'POST':
        access_code = request.form.get('access_code', '').strip()
        configured_access_code = current_app.config.get('TEACHER_ACCESS_CODE', '').strip()
        if not configured_access_code:
            flash('Teacher access code is not configured. Set TEACHER_ACCESS_CODE in your environment.', 'danger')
            return render_template('teacher_signup.html', subject_options=SUBJECT_OPTIONS)

        if access_code != configured_access_code:
            flash('Invalid teacher access code.', 'danger')
            return render_template('teacher_signup.html', subject_options=SUBJECT_OPTIONS)

        email = request.form.get('email', '').strip().lower()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            if getattr(existing_user, 'role', 'student') == 'teacher':
                flash('Teacher account already exists. Please log in.', 'warning')
                return redirect(url_for('teacher.teacher_login'))

            flash('This email already belongs to a student account. Please use the student login page.', 'warning')
            return redirect(url_for('auth.login'))

        hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        selected_subject = request.form.get('subject', '').strip()
        custom_subject = request.form.get('custom_subject', '').strip()
        teacher_subject = _normalize_teacher_subject(selected_subject, custom_subject)
        user = User(
            name=request.form.get('name'),
            email=email,
            password=hashed_pw,
            role='teacher',
            subject=teacher_subject,
        )

        db.session.add(user)
        db.session.commit()
        flash('Teacher account created successfully. Please log in.', 'success')
        return redirect(url_for('teacher.teacher_login'))

    return render_template('teacher_signup.html', subject_options=SUBJECT_OPTIONS)


@teacher.route('/login', methods=['GET', 'POST'])
def teacher_login():
    if current_user.is_authenticated:
        if getattr(current_user, 'role', 'student') == 'admin':
            return redirect(url_for('admin.dashboard'))
        if getattr(current_user, 'role', 'student') == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('dash.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and getattr(user, 'role', 'student') == 'teacher':
            if bcrypt.check_password_hash(user.password, password):
                login_user(user, remember=bool(request.form.get('remember')))
                flash(f'Welcome back, {user.name}!', 'success')
                return redirect(url_for('teacher.dashboard'))

            flash('Invalid teacher password. Please try again.', 'danger')
            return render_template('teacher_login.html')

        if user and getattr(user, 'role', 'student') == 'student':
            flash('This email belongs to a student account. Please use the student login page.', 'warning')
            return redirect(url_for('auth.login'))

        flash('Teacher account not found. Please sign up first.', 'danger')
        return redirect(url_for('teacher.teacher_signup'))

    return render_template('teacher_login.html')


@teacher.route('/logout')
def teacher_logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('teacher.teacher_login'))


@teacher.route('/dashboard')
@teacher_required
def dashboard():
    active_view = (request.args.get('view', 'overview') or 'overview').strip().lower()
    allowed_views = {'overview', 'attendance', 'students', 'homework', 'notes'}
    if active_view not in allowed_views:
        active_view = 'overview'

    students = _student_query().order_by(User.name.asc()).all()
    today = datetime.now().date()
    current_subject = _teacher_subject(current_user)

    attendance_columns = [
        Attendance.id.label('id'),
        Attendance.date.label('date'),
        Attendance.subject.label('subject'),
        Attendance.status.label('status'),
        Attendance.remarks.label('remarks'),
        Attendance.approval_status.label('approval_status'),
        Attendance.approved_at.label('approved_at'),
        Attendance.user_id.label('user_id'),
        User.name.label('student_name'),
        User.student_id.label('student_id'),
    ]

    approved_rows = (
        db.session.query(*attendance_columns)
        .outerjoin(User, Attendance.user_id == User.id)
        .filter(Attendance.approval_status == 'Approved')
        .filter(subject_match_clause(Attendance.subject, current_subject))
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .limit(50)
        .all()
    )
    pending_rows = (
        db.session.query(*attendance_columns)
        .outerjoin(User, Attendance.user_id == User.id)
        .filter(Attendance.approval_status == 'Pending')
        .filter(subject_match_clause(Attendance.subject, current_subject))
        .order_by(Attendance.date.asc(), Attendance.id.asc())
        .limit(50)
        .all()
    )

    present_counts = {
        row.user_id: row.total
        for row in db.session.query(
            Attendance.user_id,
            db.func.count(Attendance.id).label('total')
        ).filter(
            Attendance.approval_status == 'Approved',
            subject_match_clause(Attendance.subject, current_subject),
            Attendance.status == 'Present'
        ).group_by(Attendance.user_id).all()
    }
    approved_counts = {
        row.user_id: row.total
        for row in db.session.query(
            Attendance.user_id,
            db.func.count(Attendance.id).label('total')
        ).filter(
            Attendance.approval_status == 'Approved',
            subject_match_clause(Attendance.subject, current_subject)
        ).group_by(Attendance.user_id).all()
    }
    pending_counts = {
        row.user_id: row.total
        for row in db.session.query(
            Attendance.user_id,
            db.func.count(Attendance.id).label('total')
        ).filter(
            Attendance.approval_status == 'Pending',
            subject_match_clause(Attendance.subject, current_subject)
        ).group_by(Attendance.user_id).all()
    }

    student_summary = []
    for student in students:
        approved_total = approved_counts.get(student.id, 0)
        present_total = present_counts.get(student.id, 0)
        pending_total = pending_counts.get(student.id, 0)
        rate = round((present_total / approved_total) * 100, 1) if approved_total else 0.0
        student_summary.append({
            'student': student,
            'approved_total': approved_total,
            'present_total': present_total,
            'pending_total': pending_total,
            'attendance_rate': rate,
            'needs_attention': approved_total > 0 and rate < 75,
        })

    student_summary.sort(key=lambda item: (not item['needs_attention'], item['attendance_rate'], item['student'].name or ''))
    at_risk_students = [item for item in student_summary if item['needs_attention']]

    homework_items = (
        Homework.query
        .filter(subject_match_clause(Homework.subject, current_subject))
        .order_by(Homework.due_date.is_(None), Homework.due_date.asc(), Homework.created_at.desc())
        .all()
    )
    homework_recent = homework_items[:6]

    teacher_notes = (
        TeacherNote.query
        .filter(TeacherNote.teacher_id == current_user.id)
        .order_by(TeacherNote.created_at.desc())
        .limit(6)
        .all()
    )
    teacher_notes_count = TeacherNote.query.filter_by(teacher_id=current_user.id).count()

    total_students = len(students)
    total_attendance_logs = Attendance.query.filter(subject_match_clause(Attendance.subject, current_subject)).count()
    total_homeworks = len(homework_items)
    total_teacher_notes = teacher_notes_count
    pending_count = len(pending_rows)
    approved_total = sum(approved_counts.values())
    present_total = sum(present_counts.values())
    pending_total = sum(pending_counts.values())
    rejected_total = (
        Attendance.query
        .filter_by(approval_status='Rejected')
        .filter(subject_match_clause(Attendance.subject, current_subject))
        .count()
    )
    approval_rate = round((approved_total / total_attendance_logs) * 100, 1) if total_attendance_logs else 0.0
    attendance_rate = round((present_total / approved_total) * 100, 1) if approved_total else 0.0
    recent_pending_rows = pending_rows[:5]
    recent_approved_rows = approved_rows[:5]
    focus_students = student_summary[:6]
    chart_labels = ['Approved', 'Pending', 'Rejected']
    chart_values = [approved_total, pending_total, rejected_total]
    presence_labels = ['Present', 'Absent']
    presence_values = [present_total, max(approved_total - present_total, 0)]
    approved_today = (
        Attendance.query
        .filter_by(date=today, approval_status='Approved')
        .filter(subject_match_clause(Attendance.subject, current_subject))
        .count()
    )

    return render_template(
        'teacher_dashboard.html',
        students=students,
        attendance_rows=approved_rows,
        pending_rows=pending_rows,
        homework_items=homework_recent,
        teacher_notes=teacher_notes,
        student_summary=student_summary,
        at_risk_students=at_risk_students,
        total_students=total_students,
        total_attendance_logs=total_attendance_logs,
        total_homeworks=total_homeworks,
        total_teacher_notes=total_teacher_notes,
        pending_count=pending_count,
        approved_total=approved_total,
        pending_total=pending_total,
        rejected_total=rejected_total,
        approval_rate=approval_rate,
        attendance_rate=attendance_rate,
        approved_today=approved_today,
        recent_pending_rows=recent_pending_rows,
        recent_approved_rows=recent_approved_rows,
        focus_students=focus_students,
        chart_labels=chart_labels,
        chart_values=chart_values,
        presence_labels=presence_labels,
        presence_values=presence_values,
        active_view=active_view,
        now=datetime.now(),
        current_subject=current_subject,
    )


@teacher.route('/vault')
@teacher_required
def vault():
    current_subject = _teacher_subject(current_user)
    search = request.args.get('q', '').strip()

    notes_query = TeacherNote.query.filter_by(teacher_id=current_user.id)
    if search:
        like_pattern = f"%{search}%"
        notes_query = notes_query.filter(
            or_(
                TeacherNote.title.ilike(like_pattern),
                TeacherNote.content.ilike(like_pattern),
                TeacherNote.subject.ilike(like_pattern),
                TeacherNote.attachment_name.ilike(like_pattern),
            )
        )

    notes = notes_query.order_by(TeacherNote.created_at.desc()).all()
    attachment_count = sum(1 for note in notes if note.attachment_path)

    return render_template(
        'teacher_vault.html',
        notes=notes,
        current_subject=current_subject,
        search=search,
        note_count=len(notes),
        attachment_count=attachment_count,
        now=datetime.now(),
    )


@teacher.route('/attendance/export')
@teacher_required
def export_attendance():
    current_subject = _teacher_subject(current_user)
    rows = (
        db.session.query(Attendance, User)
        .outerjoin(User, Attendance.user_id == User.id)
        .filter(subject_match_clause(Attendance.subject, current_subject))
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .all()
    )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
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
    ])
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
            'date': attendance.date.strftime('%Y-%m-%d') if attendance.date else '',
            'approved_by': approved_by_user.name if approved_by_user else '',
            'approved_at': attendance.approved_at.strftime('%Y-%m-%d %H:%M:%S') if attendance.approved_at else '',
        })

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{current_subject.lower().replace(" ", "_")}_attendance_records.csv',
    )


@teacher.route('/attendance/<int:attendance_id>/remark', methods=['POST'])
@teacher_required
def update_remark(attendance_id):
    log = Attendance.query.get_or_404(attendance_id)
    if not subjects_match(log.subject, _teacher_subject(current_user)):
        flash('You can only edit remarks for your subject.', 'danger')
        return redirect(url_for('teacher.dashboard', view='attendance'))
    remark = request.form.get('remarks', '').strip()
    log.remarks = remark or None
    db.session.commit()
    sync_attendance_sheet()
    flash('Student remark updated.', 'success')
    return redirect(url_for('teacher.dashboard', view='attendance'))


@teacher.route('/attendance/<int:attendance_id>/approve', methods=['POST'])
@teacher_required
def approve_attendance(attendance_id):
    log = Attendance.query.get_or_404(attendance_id)
    if not subjects_match(log.subject, _teacher_subject(current_user)):
        flash('You can only approve attendance for your subject.', 'danger')
        return redirect(url_for('teacher.dashboard', view='attendance'))
    log.approval_status = 'Approved'
    log.approved_by = current_user.id
    log.approved_at = datetime.now()
    db.session.commit()
    sync_attendance_sheet()
    flash('Attendance approved.', 'success')
    return redirect(url_for('teacher.dashboard', view='attendance'))


@teacher.route('/attendance/<int:attendance_id>/reject', methods=['POST'])
@teacher_required
def reject_attendance(attendance_id):
    log = Attendance.query.get_or_404(attendance_id)
    if not subjects_match(log.subject, _teacher_subject(current_user)):
        flash('You can only reject attendance for your subject.', 'danger')
        return redirect(url_for('teacher.dashboard', view='attendance'))
    log.approval_status = 'Rejected'
    log.approved_by = current_user.id
    log.approved_at = datetime.now()
    db.session.commit()
    sync_attendance_sheet()
    flash('Attendance rejected.', 'warning')
    return redirect(url_for('teacher.dashboard', view='attendance'))


@teacher.route('/homework/create', methods=['POST'])
@teacher_required
def create_homework():
    subject = _teacher_subject(current_user)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    due_date_raw = request.form.get('due_date', '').strip()

    if not title:
        flash('Title is required.', 'danger')
        return redirect(url_for('teacher.dashboard', view='homework'))

    due_date = None
    if due_date_raw:
        try:
            due_date = datetime.strptime(due_date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid due date format.', 'danger')
            return redirect(url_for('teacher.dashboard', view='homework'))

    item = Homework(
        subject=subject,
        title=title,
        description=description or None,
        due_date=due_date,
        teacher_id=current_user.id,
    )
    db.session.add(item)
    db.session.commit()
    flash('Homework created.', 'success')
    return redirect(url_for('teacher.dashboard', view='homework'))


@teacher.route('/notes/create', methods=['POST'])
@teacher_required
def create_teacher_note():
    subject = _teacher_subject(current_user)
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    attachment = request.files.get('attachment')

    if not title:
        flash('Title is required.', 'danger')
        return redirect(url_for('teacher.dashboard', view='notes'))

    has_content = bool(content)
    has_attachment = bool(attachment and attachment.filename)

    if not has_content and not has_attachment:
        flash('Add note text or upload a file.', 'danger')
        return redirect(url_for('teacher.dashboard', view='notes'))

    attachment_name = None
    attachment_path = None
    if has_attachment:
        original_name = secure_filename(attachment.filename)
        unique_name = f"{uuid4().hex}_{original_name}"
        folder = _teacher_notes_folder()
        file_path = os.path.join(folder, unique_name)
        attachment.save(file_path)
        attachment_name = original_name
        attachment_path = f"uploads/teacher_notes/{unique_name}"

    note = TeacherNote(
        teacher_id=current_user.id,
        subject=subject,
        title=title,
        content=content or None,
        attachment_name=attachment_name,
        attachment_path=attachment_path,
    )
    db.session.add(note)
    db.session.commit()
    flash('Teacher note sent to your subject group.', 'success')
    return redirect(url_for('teacher.dashboard', view='notes'))


@teacher.route('/notes/<int:note_id>/delete', methods=['POST'])
@teacher_required
def delete_teacher_note(note_id):
    note = TeacherNote.query.get_or_404(note_id)
    if note.teacher_id != current_user.id:
        flash('You can only delete your own notes.', 'danger')
        return redirect(url_for('teacher.vault'))

    if note.attachment_path:
        file_path = _resolve_static_relative_path(note.attachment_path)
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except Exception as exc:
                print(f"Teacher vault file delete error: {exc}")

    db.session.delete(note)
    db.session.commit()
    flash('Teacher note removed from the vault.', 'info')
    return redirect(url_for('teacher.vault'))


@teacher.route('/homework/<int:homework_id>/update', methods=['POST'])
@teacher_required
def update_homework(homework_id):
    item = Homework.query.get_or_404(homework_id)
    if not subjects_match(item.subject, _teacher_subject(current_user)):
        flash('You can only edit homework for your subject.', 'danger')
        return redirect(url_for('teacher.dashboard', view='homework'))
    item.title = request.form.get('title', '').strip() or item.title
    item.description = request.form.get('description', '').strip() or None

    due_date_raw = request.form.get('due_date', '').strip()
    if due_date_raw:
        try:
            item.due_date = datetime.strptime(due_date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid due date format.', 'danger')
            return redirect(url_for('teacher.dashboard', view='homework'))
    else:
        item.due_date = None

    db.session.commit()
    flash('Homework updated.', 'success')
    return redirect(url_for('teacher.dashboard', view='homework'))


@teacher.route('/homework/<int:homework_id>/delete', methods=['POST'])
@teacher_required
def delete_homework(homework_id):
    item = Homework.query.get_or_404(homework_id)
    db.session.delete(item)
    db.session.commit()
    flash('Homework deleted.', 'info')
    return redirect(url_for('teacher.dashboard', view='homework'))
