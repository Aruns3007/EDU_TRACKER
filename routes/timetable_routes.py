from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from extensions import db
from models.timetable_model import Timetable
from routes.access_control import student_required
from services.subject_utils import normalize_subject

time_table = Blueprint('time_table', __name__)

@time_table.route('/timetable')
@student_required
def view_timetable():
    college_schedule = Timetable.query.filter_by(user_id=current_user.id, category='college').order_by(Timetable.day, Timetable.start_time).all()
    study_schedule = Timetable.query.filter_by(user_id=current_user.id, category='study').order_by(Timetable.day, Timetable.start_time).all()
    return render_template('timetable.html', college_schedule=college_schedule, study_schedule=study_schedule)

@time_table.route('/timetable/add', methods=['POST'])
@student_required
def add_schedule():
    subject = normalize_subject(request.form.get('subject'))
    day = normalize_subject(request.form.get('day'))
    start_time = normalize_subject(request.form.get('start_time'))
    end_time = normalize_subject(request.form.get('end_time'))
    category = (request.form.get('category') or 'college').strip().lower()

    if subject and day and start_time and end_time:
        new_entry = Timetable(
            subject=subject,
            day=day,
            start_time=start_time,
            end_time=end_time,
            category=category if category in ['college', 'study'] else 'college',
            user_id=current_user.id
        )
        db.session.add(new_entry)
        db.session.commit()
        flash('Schedule added successfully!', 'success')
    else:
        flash('All fields are required.', 'danger')
        
    return redirect(url_for('time_table.view_timetable'))

@time_table.route('/timetable/delete/<int:id>')
@student_required
def delete_schedule(id):
    entry = Timetable.query.get_or_404(id)
    if entry.user_id == current_user.id:
        db.session.delete(entry)
        db.session.commit()
        flash('Schedule removed.', 'info')
    return redirect(url_for('time_table.view_timetable'))
