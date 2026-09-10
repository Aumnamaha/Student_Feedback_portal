"""Tests for admin reports route — aggregate stats with PII protection.

Run with: pytest test_reports.py -v
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"


from app import create_app
from config import Config
from models import User, Feedback, db


def _make_app():
    """Create a Flask test app with in-memory SQLite."""

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "test-secret-key"
        WTF_CSRF_ENABLED = False

    return create_app(TestConfig)


def _seed_reports_data(app):
    """Create admin + students + feedback spread across categories/months."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        alice = User(
            name="Alice Smith",
            email="alice@stu.edu",
            roll_number="CS2024001",
            role="student",
        )
        alice.set_password("pass123")
        db.session.add(alice)

        bob = User(
            name="Bob Jones",
            email="bob@stu.edu",
            roll_number="CS2024002",
            role="student",
        )
        bob.set_password("pass123")
        db.session.add(bob)
        db.session.flush()

        # Food feedback (various ratings, some anonymous)
        f1 = Feedback(student_id=alice.id, category="Food", rating=4, comment="Good food.", status="Pending")
        f2 = Feedback(student_id=bob.id, category="Food", rating=3, comment="Average canteen.", is_anonymous=True, status="In Progress")
        f3 = Feedback(student_id=alice.id, category="Food", rating=5, comment="Best food ever!", status="Resolved")
        db.session.add_all([f1, f2, f3])

        # Faculty feedback
        f4 = Feedback(student_id=bob.id, category="Faculty", rating=2, comment="Poor teaching.", is_anonymous=True, status="Pending")
        f5 = Feedback(student_id=alice.id, category="Faculty", rating=5, comment="Great professor!", status="Resolved")
        db.session.add_all([f4, f5])

        # Infrastructure feedback
        f6 = Feedback(student_id=bob.id, category="Infrastructure", rating=1, comment="Broken AC.", is_anonymous=True, status="In Progress")
        db.session.add(f6)

        db.session.commit()


# ------------------------------------------------------------------ #
#  ACCESS PROTECTION                                                   #
# ------------------------------------------------------------------ #

def test_reports_requires_login():
    """Unauthenticated user cannot access /reports."""
    app = _make_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.get("/admin/reports")
    assert resp.status_code == 302


def test_reports_requires_admin_role():
    """Student cannot access /reports."""
    app = _make_app()
    with app.app_context():
        db.create_all()

        student = User(name="Std", email="std@test.com", role="student")
        student.set_password("pass123")
        db.session.add(student)
        db.session.commit()

    client = app.test_client()
    client.post("/login", data={"email": "std@test.com", "password": "pass123"})
    resp = client.get("/admin/reports")
    assert resp.status_code == 302


# ------------------------------------------------------------------ #
#  AGGREGATE QUERIES                                                   #
# ------------------------------------------------------------------ #

def test_reports_shows_category_stats():
    """Reports page returns category stats with avg rating and count."""
    app = _make_app()
    _seed_reports_data(app)
    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )
        assert resp.status_code == 302

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    # Should contain all three categories
    assert "Food" in html
    assert "Faculty" in html
    assert "Infrastructure" in html


def test_reports_shows_status_counts():
    """Reports page returns status count breakdown."""
    app = _make_app()
    _seed_reports_data(app)
    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    # Should contain all three statuses
    assert "Pending" in html
    assert "In Progress" in html
    assert "Resolved" in html


def test_reports_shows_monthly_trend():
    """Reports page returns monthly trend data."""
    app = _make_app()
    _seed_reports_data(app)
    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    # Should contain trend bars (CSS bar indicators)
    assert "Count" in html


def test_reports_shows_weekly_trend():
    """Reports page returns weekly trend data."""
    app = _make_app()
    _seed_reports_data(app)
    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    # Should contain weekly section header
    assert "Weekly Trend" in html


def test_reports_empty_data():
    """Reports page handles empty database gracefully."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")

    # Should show empty-state messages, not crash
    assert "No feedback data available" in html


# ------------------------------------------------------------------ #
#  PII PROTECTION — NO USER DATA IN RESPONSE                           #
# ------------------------------------------------------------------ #

def test_reports_no_pii_in_response():
    """Reports HTML must NEVER contain student PII (no joins to users)."""
    app = _make_app()
    _seed_reports_data(app)
    with app.test_client() as client:
        resp = client.post(
            "/login", data={"email": "admin@test.com", "password": "admin123"}
        )

        resp = client.get("/admin/reports")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

    # Student PII must never appear in the reports response
    assert "Alice Smith" not in body, (
        f"PII LEAK: 'Alice Smith' found in reports HTML"
    )
    assert "Bob Jones" not in body, (
        f"PII LEAK: 'Bob Jones' found in reports HTML"
    )
    assert "alice@stu.edu" not in body, (
        "PII LEAK: email found in reports HTML"
    )
    assert "bob@stu.edu" not in body, (
        "PII LEAK: email found in reports HTML"
    )
    assert "CS2024001" not in body, (
        "PII LEAK: roll number found in reports HTML"
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
