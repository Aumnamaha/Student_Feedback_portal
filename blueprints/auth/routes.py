"""Authentication routes: /register, /login, logout."""

from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import User, db

# Import the blueprint from the parent module (avoids circular imports)
from . import auth_bp


# ------------------------------------------------------------------ #
#  REGISTER                                                            #
# ------------------------------------------------------------------ #

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Student registration page."""

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        roll_number = request.form.get('roll_number', '').strip() or None
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # --- validation ---
        if not name or not email or not password:
            flash('Name, email, and password are required.', 'error')
            return render_template('register.html')

        if '@' not in email:
            flash('Invalid email address.', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        # --- check uniqueness (roll_number can be None) ---
        existing = User.query.filter(
            User.email == email
        ).first()
        if existing:
            flash('Email already registered.', 'error')
            return render_template('register.html')

        if roll_number:
            dup_roll = User.query.filter_by(roll_number=roll_number).first()
            if dup_roll:
                flash('Roll number already registered.', 'error')
                return render_template('register.html')

        # --- create user (student by default) ---
        user = User(
            name=name,
            email=email,
            roll_number=roll_number,
            role='student',
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


# ------------------------------------------------------------------ #
#  LOGIN                                                               #
# ------------------------------------------------------------------ #

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page — supports student, admin, and faculty roles."""

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('login.html')

        # --- try student/admin (User) first ---
        user = User.query.filter_by(email=email).first()
        role_type = None

        if user is not None and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            role_type = 'user'

        # --- try faculty if User didn't match ---
        if role_type is None:
            from models import Faculty
            faculty = Faculty.query.filter_by(email=email).first()
            if faculty is not None and faculty.check_password(password):
                session['faculty_id'] = faculty.id
                session['role'] = 'faculty'
                session['name'] = faculty.name
                role_type = 'faculty'

        # --- invalid credentials ---
        if role_type is None:
            flash('Invalid email or password.', 'error')
            return render_template('login.html')

        flash(f'Welcome back, {session["name"]}!', 'success')

        # redirect based on role
        if session['role'] == 'admin':
            return redirect(url_for('admin.dashboard'))
        if session['role'] == 'faculty':
            # Placeholder — faculty dashboard route not yet implemented
            flash(
                'Faculty dashboard is under construction.',
                'warning',
            )
            return redirect(url_for('auth.login'))
        return redirect(url_for('student.dashboard'))

    return render_template('login.html')


# ------------------------------------------------------------------ #
#  LOGOUT                                                              #
# ------------------------------------------------------------------ #

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Clear session and log out."""
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))


# ------------------------------------------------------------------ #
#  LOGIN / ADMIN REQUIRED DECORATORS                                   #
# ------------------------------------------------------------------ #

def login_required(f):
    """Decorator that redirects unauthenticated users to /login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session and 'faculty_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator that requires the user to have the admin role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def faculty_required(f):
    """Decorator that requires the user to have the faculty role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'faculty_id' not in session or session.get('role') != 'faculty':
            flash('Faculty access required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# Expose decorators for import by other blueprints
__all__ = ['login_required', 'admin_required', 'faculty_required']
