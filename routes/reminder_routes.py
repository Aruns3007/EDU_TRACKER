from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from models.timetable_model import Timetable
from services.subject_utils import normalize_subject, subject_match_clause

reminders = Blueprint('reminders', __name__)

DAY_INDEX = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}

LOOKAHEAD_MINUTES = 15


def _parse_time(value):
    if not value:
        return None
    for fmt in ('%H:%M', '%I:%M %p'):
        try:
            return datetime.strptime(value.strip(), fmt).time()
        except ValueError:
            continue
    return None


def _next_occurrence(entry, now):
    day_name = (entry.day or '').strip().lower()
    start_time = _parse_time(entry.start_time)
    if day_name not in DAY_INDEX or start_time is None:
        return None

    days_ahead = (DAY_INDEX[day_name] - now.weekday()) % 7
    candidate_date = now.date() + timedelta(days=days_ahead)
    candidate_start = datetime.combine(candidate_date, start_time)

    if candidate_start < now:
        candidate_start += timedelta(days=7)

    return candidate_start


def _event_key(entry, occurrence_start):
    return ':'.join([
        str(getattr(entry, 'id', '0')),
        (entry.subject or '').strip().lower(),
        (entry.day or '').strip().lower(),
        (entry.start_time or '').strip(),
        (entry.end_time or '').strip(),
        occurrence_start.date().isoformat(),
    ])


def _build_reminder(entry, now, audience):
    occurrence_start = _next_occurrence(entry, now)
    if occurrence_start is None:
        return None

    minutes_left = int((occurrence_start - now).total_seconds() // 60)
    if minutes_left < 0 or minutes_left > LOOKAHEAD_MINUTES:
        return None

    subject = (entry.subject or 'Class').strip()
    start_label = occurrence_start.strftime('%I:%M %p').lstrip('0')
    audience_label = 'teacher' if audience == 'teacher' else 'student'
    title = 'Teaching reminder' if audience == 'teacher' else 'Next class starting soon'
    message = (
        f'Your {subject} class starts at {start_label} on {entry.day}.'
        if audience_label == 'teacher'
        else f'Next class: {subject} starts at {start_label} on {entry.day}.'
    )

    return {
        'id': _event_key(entry, occurrence_start),
        'title': title,
        'message': message,
        'subject': subject,
        'day': entry.day,
        'start_time': entry.start_time,
        'end_time': entry.end_time,
        'minutes_left': minutes_left,
        'audience': audience_label,
    }


@reminders.route('/api/class-reminders')
@login_required
def class_reminders():
    now = datetime.now()
    role = getattr(current_user, 'role', 'student') or 'student'

    if role == 'teacher':
        teacher_subject = normalize_subject(getattr(current_user, 'subject', ''))
        if not teacher_subject:
            return jsonify({'reminders': [], 'role': role})

        schedule_rows = Timetable.query.filter(subject_match_clause(Timetable.subject, teacher_subject)).all()
        unique_rows = []
        seen_slots = set()
        for row in schedule_rows:
            slot_key = (
                (row.subject or '').strip().lower(),
                (row.day or '').strip().lower(),
                (row.start_time or '').strip(),
                (row.end_time or '').strip(),
                (row.category or '').strip().lower(),
            )
            if slot_key in seen_slots:
                continue
            seen_slots.add(slot_key)
            unique_rows.append(row)

        reminders_list = []
        for row in unique_rows:
            reminder = _build_reminder(row, now, 'teacher')
            if reminder:
                reminders_list.append(reminder)

    else:
        schedule_rows = Timetable.query.filter_by(user_id=current_user.id).all()
        reminders_list = []
        for row in schedule_rows:
            reminder = _build_reminder(row, now, 'student')
            if reminder:
                reminders_list.append(reminder)

    reminders_list.sort(key=lambda item: (item['minutes_left'], item['day'], item['start_time']))

    return jsonify({
        'reminders': reminders_list[:3],
        'role': role,
    })
