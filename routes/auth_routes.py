from flask import Blueprint, render_template, url_for, flash, redirect, request
from extensions import db, bcrypt
from models.user_model import User
from flask_login import login_user, current_user, logout_user

auth = Blueprint('auth', __name__)

@auth.route("/register", methods=['GET', 'POST'])
def register():
    # If already logged in, skip registration
    if current_user.is_authenticated:
        if getattr(current_user, 'role', 'student') == 'admin':
            return redirect(url_for('admin.dashboard'))
        if getattr(current_user, 'role', 'student') == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('dash.dashboard'))
        
    if request.method == 'POST':
        # 1. Check if user already exists
        email = request.form.get('email', '').strip().lower()
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('auth.login'))

        # 2. Hash password and create user
        hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        user = User(
            name=request.form.get('name'),
            email=email,
            password=hashed_pw,
            student_id=request.form.get('student_id'),
            role='student'
        )
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            
    return render_template('register.html')

@auth.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if getattr(current_user, 'role', 'student') == 'admin':
            return redirect(url_for('admin.dashboard'))
        if getattr(current_user, 'role', 'student') == 'teacher':
            return redirect(url_for('teacher.dashboard'))
        return redirect(url_for('dash.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        # Verify user and password
        if user and bcrypt.check_password_hash(user.password, password):
            role = getattr(user, 'role', 'student') or 'student'
            if role in {'student', 'admin'}:
                login_user(user, remember=bool(request.form.get('remember')))
                next_page = request.args.get('next')
                flash(f'Welcome back, {user.name}!', 'success')
                if next_page:
                    return redirect(next_page)
                if role == 'admin':
                    return redirect(url_for('admin.dashboard'))
                return redirect(url_for('dash.dashboard'))
            if role == 'teacher':
                flash('This is the student login. Please use the teacher login page.', 'warning')
                return redirect(url_for('teacher.teacher_login'))
        else:
            flash('Login Unsuccessful. Please check your email and password.', 'danger')
            
    return render_template('login.html')

@auth.route("/logout")
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
