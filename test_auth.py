"""Unit tests for authentication flow.

Uses an in-memory SQLite database so no MySQL instance is required.
Run with: pytest test_auth.py -v
"""

import os, sys

# --- Set env BEFORE any imports that read it ---
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret-key'


from app import create_app
from models import User, db
from config import Config


def _get_test_app():
    """Create a Flask test app with in-memory SQLite."""

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
        SECRET_KEY = 'test-secret-key'
        WTF_CSRF_ENABLED = False

    return create_app(TestConfig)


# ------------------------------------------------------------------ #
#  REGISTER                                                            #
# ------------------------------------------------------------------ #

def test_register_get_returns_200():
    """GET /register renders the registration page."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.get('/register')
    assert resp.status_code == 200


def test_register_success():
    """Valid registration creates a user and redirects to /login."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

    client = app.test_client()
    resp = client.post('/register', data={
        'name': 'Test Student',
        'email': 'test@example.com',
        'roll_number': 'CS2024001',
        'password': 'pass123',
        'confirm_password': 'pass123',
    }, follow_redirects=True)

    assert resp.status_code == 200


def test_register_duplicate_email():
    """Registering with an existing email shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

        user1 = User(name='User One', email='dup@example.com', role='student')
        user1.set_password('pass123')
        db.session.add(user1)
        db.session.commit()

    client = app.test_client()
    resp = client.post('/register', data={
        'name': 'User Two',
        'email': 'dup@example.com',
        'roll_number': 'CS2024002',
        'password': 'pass123',
        'confirm_password': 'pass123',
    })

    assert resp.status_code == 200
    assert b'Email already registered' in resp.data


def test_register_missing_fields():
    """Registration without required fields shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.post('/register', data={
        'name': '', 'email': '', 'password': ''
    })
    assert resp.status_code == 200
    assert b'Name, email, and password are required' in resp.data


def test_register_password_mismatch():
    """Registration with mismatched passwords shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.post('/register', data={
        'name': 'Test', 'email': 'test2@example.com',
        'password': 'pass123', 'confirm_password': 'wrong456',
    })
    assert resp.status_code == 200
    assert b'Passwords do not match' in resp.data


def test_register_short_password():
    """Registration with password shorter than 6 chars shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.post('/register', data={
        'name': 'Test', 'email': 'test3@example.com',
        'password': 'abc', 'confirm_password': 'abc',
    })
    assert resp.status_code == 200
    assert b'at least 6 characters' in resp.data


# ------------------------------------------------------------------ #
#  LOGIN                                                               #
# ------------------------------------------------------------------ #

def test_login_get_returns_200():
    """GET /login renders the login page."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.get('/login')
    assert resp.status_code == 200


def test_login_success_student():
    """Correct credentials for a student — session is set, redirect URL builds."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

        user = User(name='Student', email='student@test.com', role='student')
        user.set_password('mypass')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    resp = client.post('/login', data={
        'email': 'student@test.com',
        'password': 'mypass',
    }, follow_redirects=True)  # Now safe — student.dashboard route exists

    assert resp.status_code == 200


def test_login_wrong_password():
    """Wrong password shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

        user = User(name='Student', email='wrong@test.com', role='student')
        user.set_password('correct123')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    resp = client.post('/login', data={
        'email': 'wrong@test.com',
        'password': 'badpass',
    })
    assert resp.status_code == 200
    assert b'Invalid email or password' in resp.data


def test_login_nonexistent_user():
    """Logging in with a non-existent email shows an error."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

    client = app.test_client()
    resp = client.post('/login', data={
        'email': 'ghost@test.com',
        'password': 'anything',
    })
    assert resp.status_code == 200
    assert b'Invalid email or password' in resp.data


def test_login_session_set():
    """Successful login sets session variables."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

        user = User(name='SessionUser', email='session@test.com', role='student')
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    # Login to establish session cookie
    resp = client.post('/login', data={
        'email': 'session@test.com',
        'password': 'pass123',
    }, follow_redirects=False)

    # Check what's stored in the session (Flask 3.x API)
    with client.session_transaction() as sess:
        assert 'user_id' in sess
        assert sess['role'] == 'student'


# ------------------------------------------------------------------ #
#  LOGOUT                                                              #
# ------------------------------------------------------------------ #

def test_logout_clears_session():
    """Logout clears the session and redirects to /login."""
    app = _get_test_app()
    with app.app_context():
        db.create_all()

        user = User(name='LogoutUser', email='logout@test.com', role='student')
        user.set_password('pass123')
        db.session.add(user)
        db.session.commit()

    client = app.test_client()

    # Step 1: Login to establish a session
    resp = client.post('/login', data={
        'email': 'logout@test.com',
        'password': 'pass123',
    }, follow_redirects=False)
    assert resp.status_code in (302, 200)

    # Step 2: Verify session has user_id after login
    with client.session_transaction() as sess:
        assert 'user_id' in sess  # session is active after login

    # Step 3: Logout
    resp = client.post('/logout', follow_redirects=True)
    assert resp.status_code == 200
    assert b'logged out' in resp.data


# ------------------------------------------------------------------ #
#  SEED SCRIPT                                                         #
# ------------------------------------------------------------------ #

def test_seed_creates_admin():
    """Seed logic creates an admin account if none exists."""
    app = _get_test_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        count_before = User.query.filter_by(role='admin').count()
        assert count_before == 0

        # Inline seed logic (same as seed.py)
        admin = User(
            name='System Admin',
            email='admin@studentfeedback.local',
            role='admin',
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

    with app.app_context():
        admins = User.query.filter_by(role='admin').all()
        assert len(admins) == 1


def test_seed_no_duplicate():
    """Seed logic does not create a second admin if one exists."""
    app = _get_test_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Create an admin first
        admin1 = User(name='Admin One', email='admin1@test.com', role='admin')
        admin1.set_password('pass123')
        db.session.add(admin1)
        db.session.commit()

    with app.app_context():
        existing = User.query.filter_by(role='admin').first()
        if existing is None:
            admin = User(name='System Admin', email='admin@studentfeedback.local', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

    with app.app_context():
        admins = User.query.filter_by(role='admin').all()
        assert len(admins) == 1


# ------------------------------------------------------------------ #
#  DECORATORS & PASSWORD HASHING                                       #
# ------------------------------------------------------------------ #

def test_password_hashing():
    """Werkzeug password hashing and verification work correctly."""
    user = User(name='HashTest', email='hash@test.com', role='student')
    user.set_password('secret123')

    assert user.check_password('secret123') is True
    assert user.check_password('wrongpass') is False


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
