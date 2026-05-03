from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user


def _user_role(user):
    return getattr(user, 'role', 'student') or 'student'


def student_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))

        if _user_role(current_user) != 'student':
            flash('This area is reserved for students.', 'warning')
            return redirect(url_for('teacher.dashboard'))

        return view(*args, **kwargs)

    return wrapped


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('teacher.teacher_login'))

        if _user_role(current_user) != 'teacher':
            flash('Teacher access required.', 'warning')
            return redirect(url_for('auth.login'))

        return view(*args, **kwargs)

    return wrapped
