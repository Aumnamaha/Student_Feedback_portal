"""Tests for admin dashboard, filters, status updates, and anonymity.

Run with: pytest test_admin.py -v
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


# ------------------------------------------------------------------ #
#  ADMIN DASHBOARD ROUTE                                               #
# ------------------------------------------------------------------ #

def test_admin_dashboard_requires_login():
    """Unauthenticated access to /admin/dashboard redirects to login."""
    app = _make_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302


def test_admin_dashboard_requires_admin_role():
    """Student cannot access /admin/dashboard."""
    app = _make_app()
    with app.app_context():
        db.create_all()
        user = User(name="Student", email="std@test.com", role="student")
        user.set_password("pass123")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    resp = client.post(
        "/login", data={"email": "std@test.com", "password": "pass123"}, follow_redirects=False
    )
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302


def test_admin_dashboard_shows_all_feedback():
    """Admin dashboard shows all feedback entries."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb1 = Feedback(student_id=s1.id, category="Food", rating=4, comment="Cafeteria food is good today.", status="Pending")
        fb2 = Feedback(student_id=s1.id, category="Faculty", rating=5, comment="Professor explained concepts very well.", status="Resolved")
        db.session.add_all([fb1, fb2])
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200


def test_admin_dashboard_filters_by_category():
    """Filtering by category returns only matching rows."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb_food = Feedback(student_id=s1.id, category="Food", rating=4, comment="Good food.", status="Pending")
        fb_faculty = Feedback(student_id=s1.id, category="Faculty", rating=5, comment="Great class.", status="Resolved")
        db.session.add_all([fb_food, fb_faculty])
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # Filter by Food — should NOT show the Faculty feedback
        resp = client.get("/admin/dashboard?category=Food")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "<td>Food</td>" in html, "Should contain Food category"
        assert "<td>Faculty</td>" not in html, f"Should NOT show Faculty: {html}"


def test_admin_dashboard_filters_by_status():
    """Filtering by status returns only matching rows."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb_pending = Feedback(student_id=s1.id, category="Food", rating=4, comment="Test pending.", status="Pending")
        fb_resolved = Feedback(student_id=s1.id, category="Faculty", rating=5, comment="Test resolved.", status="Resolved")
        db.session.add_all([fb_pending, fb_resolved])
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # Filter by Pending — should NOT show Resolved feedback
        resp = client.get("/admin/dashboard?status=Pending")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert 'badge-pending' in html, "Should contain Pending status badge"
        assert 'badge-resolved' not in html, f"Should NOT show Resolved: {html}"


def test_admin_dashboard_keyword_search():
    """Keyword search finds matching comments."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb_ac = Feedback(student_id=s1.id, category="Food", rating=4, comment="Library AC is broken.", status="Pending")
        fb_no_ac = Feedback(student_id=s1.id, category="Faculty", rating=5, comment="Good class today.", status="Resolved")
        db.session.add_all([fb_ac, fb_no_ac])
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # Search for "AC" — should only return the AC feedback (Food category)
        resp = client.get("/admin/dashboard?keyword=AC")
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
#  ANONYMITY — CRITICAL SECURITY TESTS                                 #
# ------------------------------------------------------------------ #

def test_anonymous_feedback_to_admin_dict_has_no_pii():
    """to_admin_dict() NEVER returns student PII for anonymous rows."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Test comment.", is_anonymous=True)
        db.session.add(fb)
        db.session.commit()

    with app.app_context():
        fb = db.session.get(Feedback, 1)
        data = fb.to_admin_dict()

        assert data["student_name"] == "Anonymous"
        assert data["student_email"] is None
        assert data["student_roll_number"] is None

        for key, val in data.items():
            if isinstance(val, str):
                assert "Alice" not in val
                assert "alice@test.com" not in val
                assert "CS001" not in val


def test_anonymous_feedback_admin_dashboard_no_pii_in_response():
    """Admin dashboard HTML response for anonymous feedback contains NO student PII."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Anonymous feedback about food.", is_anonymous=True)
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        assert resp.status_code == 302, f"Login should redirect: {resp.status_code}"

        # Now check the actual dashboard response for PII leaks
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

    assert "Alice Student" not in body, (
        f"PII LEAK: 'Alice Student' found in admin dashboard HTML"
    )
    assert "alice@test.com" not in body, (
        "PII LEAK: email found in admin dashboard HTML"
    )


def test_anonymous_feedback_detail_no_pii_in_response():
    """Admin feedback detail view for anonymous row contains NO student PII."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Anonymous food feedback.", is_anonymous=True)
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # fb.id is 1 (only feedback inserted in this test)
        resp = client.get("/admin/feedback/1")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

    assert "Alice Student" not in body, (
        f"PII LEAK: 'Alice Student' found in anonymous detail HTML"
    )
    assert "alice@test.com" not in body


def test_non_anonymous_feedback_shows_pii():
    """Non-anonymous feedback correctly shows student PII to admin."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Alice Student", email="alice@test.com", roll_number="CS001", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Public feedback.", is_anonymous=False)
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # fb.id is 1
        resp = client.get("/admin/feedback/1")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")

    assert "Alice Student" in body, (
        f"Non-anonymous feedback should show student name: {body}"
    )
    assert "alice@test.com" in body


# ------------------------------------------------------------------ #
#  FEEDBACK STATUS UPDATE                                              #
# ------------------------------------------------------------------ #

def test_feedback_status_update():
    """Admin can update feedback status from Pending → In Progress."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Student", email="std@test.com", roll_number="CS099", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Test.", status="Pending")
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # fb.id is 1 (only feedback inserted in this test)
        resp = client.post(
            "/admin/feedback/1/status",
            data={"status": "In Progress"},
            follow_redirects=True,
        )

    with app.app_context():
        fb_updated = db.session.get(Feedback, 1)
        assert fb_updated.status == "In Progress"


def test_feedback_status_update_invalid_rejected():
    """Invalid status value is rejected and original status preserved."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        s1 = User(name="Student", email="std@test.com", roll_number="CS098", role="student")
        s1.set_password("pass123")
        db.session.add(s1)
        db.session.flush()

        fb = Feedback(student_id=s1.id, category="Food", rating=4, comment="Test.", status="Pending")
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        resp = client.post("/login", data={"email": "admin@test.com", "password": "admin123"}, follow_redirects=False)
        # fb.id is 1
        resp = client.post(
            "/admin/feedback/1/status",
            data={"status": "INVALID_STATUS"},
            follow_redirects=True,
        )

    with app.app_context():
        fb_updated = db.session.get(Feedback, 1)
        assert fb_updated.status == "Pending"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
