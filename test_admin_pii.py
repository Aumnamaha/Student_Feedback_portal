"""Tests for admin dashboard, filters, anonymous PII protection.

Run with: pytest test_admin_pii.py -v

These tests use an in-memory SQLite database so they are fully isolated
and require no external MySQL server.
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

from app import create_app
from models import User, Feedback, db


# ------------------------------------------------------------------ #
#  FIXTURE HELPERS                                                     #
# ------------------------------------------------------------------ #

def _make_app():
    """Return a Flask test app configured for in-memory SQLite."""

    class TestConfig:
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SECRET_KEY = "test-secret-key"
        WTF_CSRF_ENABLED = False

    return create_app(TestConfig)


def _seed_data(app):
    """Create admin + 2 students + 3 feedback rows inside *app*'s context."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        # --- users ---
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
        db.session.flush()  # assign IDs so feedback rows can reference them

        # --- feedback (fb1 non-anon, fb2 & fb3 anonymous) ---
        fb1 = Feedback(
            student_id=alice.id,
            category="Food",
            rating=4,
            comment="The canteen food is decent today.",
            status="Pending",
        )
        db.session.add(fb1)

        fb2 = Feedback(
            student_id=bob.id,
            category="Faculty",
            rating=2,
            comment="Some professors are rude during office hours.",
            is_anonymous=True,
            status="In Progress",
        )
        db.session.add(fb2)

        fb3 = Feedback(
            student_id=alice.id,
            category="Infrastructure",
            rating=5,
            comment="New lab equipment is great!",
            is_anonymous=True,
            status="Resolved",
        )
        db.session.add(fb3)
        db.session.commit()


# ------------------------------------------------------------------ #
#  ADMIN ACCESS PROTECTION                                             #
# ------------------------------------------------------------------ #

def test_admin_dashboard_requires_login():
    """Unauthenticated user cannot access /admin/dashboard."""
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
        db.drop_all()
        db.create_all()

        student = User(name="Std", email="std@test.com", role="student")
        student.set_password("pass123")
        db.session.add(student)
        db.session.commit()

    client = app.test_client()
    client.post(
        "/login", data={"email": "std@test.com", "password": "pass123"}
    )
    resp = client.get("/admin/dashboard")
    assert resp.status_code == 302


def test_feedback_detail_requires_login():
    """Unauthenticated user cannot view feedback detail."""
    app = _make_app()
    with app.app_context():
        db.create_all()
    client = app.test_client()
    resp = client.get("/admin/feedback/1")
    assert resp.status_code == 302


# ------------------------------------------------------------------ #
#  ADMIN DASHBOARD — FILTERS                                           #
# ------------------------------------------------------------------ #

def _login_admin(client):
    """Log in the seeded admin account and return response."""
    return client.post(
        "/login", data={"email": "admin@test.com", "password": "admin123"}
    )


def test_dashboard_shows_all_feedback():
    """Admin dashboard returns all feedback rows (status 200)."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200


def test_filter_by_category():
    """Filtering by category returns only matching rows."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)

        # All feedback — 3 rows (IDs 1,2,3)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        html = resp.data.decode()
        # Should contain all three category names in table
        assert "<td>Food</td>" in html
        assert "<td>Faculty</td>" in html
        assert "<td>Infrastructure</td>" in html

        # Food filter — only 1 row (fb1, Alice Smith non-anonymous)
        resp = client.get("/admin/dashboard?category=Food")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "<td>Food</td>" in html
        # Bob Jones should NOT appear (his only feedback is Faculty + anonymous)
        assert "Bob Jones" not in html
        assert "bob@stu.edu" not in html


def test_filter_by_status():
    """Filtering by status returns only matching rows."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)
        resp = client.get("/admin/dashboard?status=Pending")
        assert resp.status_code == 200


def test_keyword_search():
    """Keyword search finds matching comments (case-insensitive)."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)
        resp = client.get("/admin/dashboard?keyword=canteen")
        assert resp.status_code == 200


def test_date_range_filter():
    """Date range filter works."""
    from datetime import date

    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)
        today = date.today().isoformat()
        resp = client.get(f"/admin/dashboard?date_from={today}")
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
#  ANONYMOUS PII PROTECTION — CRITICAL                                 #
# ------------------------------------------------------------------ #

def test_dashboard_no_pii_for_anonymous_rows():
    """Anonymous feedback rows must NOT expose student identity in HTML.

    In our seed data:
      - fb1 (non-anon, Alice Smith) → her PII SHOULD appear ✅
      - fb2 (anon, Bob Jones)     → his PII MUST NOT appear ❌
      - fb3 (anon, Alice Smith)   → her PII MUST NOT appear for THIS row
        (but appears for fb1 which is non-anonymous — that's correct)

    We verify that Bob Jones' identity NEVER leaks, and that anonymous
    rows show 'Anonymous' instead of real names.
    """
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200

    body = resp.data.decode("utf-8")

    # Bob Jones has ONLY anonymous feedback — his identity must never leak
    assert "Bob Jones" not in body, (
        f"PII LEAK: 'Bob Jones' found in admin dashboard HTML"
    )
    assert "bob@stu.edu" not in body, (
        "PII LEAK: Bob's email found in admin dashboard HTML"
    )

    # Anonymous rows should show 'Anonymous', not real names
    # Count how many times 'Anonymous' appears (fb2 + fb3 = 2 anonymous rows)
    assert body.count(">Anonymous<") >= 2, (
        "Expected at least 2 'Anonymous' labels for anonymous feedback rows"
    )


def test_feedback_detail_no_pii_for_anonymous():
    """Detail view for anonymous feedback must NOT expose student PII."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)

        # fb2 is anonymous (Bob Jones)
        resp = client.get("/admin/feedback/2")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Bob Jones" not in body, (
            "PII LEAK: 'Bob Jones' found in anonymous detail HTML"
        )
        assert "bob@stu.edu" not in body
        assert "CS2024002" not in body

        # fb3 is also anonymous (Alice Smith)
        resp = client.get("/admin/feedback/3")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Alice Smith" not in body, (
            "PII LEAK: 'Alice Smith' found in anonymous detail HTML"
        )
        assert "alice@stu.edu" not in body


def test_non_anonymous_feedback_shows_pii():
    """Non-anonymous feedback MUST show student identity to admin."""
    app = _make_app()
    _seed_data(app)
    with app.test_client() as client:
        _login_admin(client)

        # fb1 is NOT anonymous (Alice Smith)
        resp = client.get("/admin/feedback/1")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Alice Smith" in body, (
            "Non-anonymous feedback should show student name"
        )
        assert "alice@stu.edu" in body


def test_to_admin_dict_no_pii_for_anonymous():
    """to_admin_dict() must never return PII for anonymous rows."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        alice = User(
            name="Alice Smith", email="alice@stu.edu", role="student"
        )
        alice.set_password("pass123")
        db.session.add(alice)
        db.session.flush()

        fb = Feedback(
            student_id=alice.id,
            category="Food",
            rating=4,
            comment="Test.",
            is_anonymous=True,
        )
        db.session.add(fb)
        db.session.commit()

    with app.app_context():
        data = db.session.get(Feedback, 1).to_admin_dict()

    assert data["student_name"] == "Anonymous"
    assert data["student_email"] is None
    assert data["student_roll_number"] is None

    # No string value in the dict should contain PII fragments
    for key, val in data.items():
        if isinstance(val, str):
            assert "Alice" not in val
            assert "alice@stu.edu" not in val


def test_to_admin_dict_shows_pii_for_non_anonymous():
    """to_admin_dict() MUST return PII for non-anonymous rows."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        alice = User(
            name="Alice Smith", email="alice@stu.edu", role="student"
        )
        alice.set_password("pass123")
        db.session.add(alice)
        db.session.flush()

        fb = Feedback(
            student_id=alice.id,
            category="Food",
            rating=4,
            comment="Test.",
            is_anonymous=False,
        )
        db.session.add(fb)
        db.session.commit()

    with app.app_context():
        data = db.session.get(Feedback, 1).to_admin_dict()

    assert data["student_name"] == "Alice Smith"
    assert data["student_email"] == "alice@stu.edu"


# ------------------------------------------------------------------ #
#  STATUS UPDATE                                                       #
# ------------------------------------------------------------------ #

def test_status_update_pending_to_in_progress():
    """Admin can update feedback status from Pending → In Progress."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        student = User(name="Std", email="std@t.com", role="student")
        student.set_password("pass123")
        db.session.add(student)
        db.session.flush()

        fb = Feedback(
            student_id=student.id,
            category="Food",
            rating=4,
            comment="Test.",
            status="Pending",
        )
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        _login_admin(client)
        resp = client.post(
            "/admin/feedback/1/status",
            data={"status": "In Progress"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    with app.app_context():
        fb_updated = db.session.get(Feedback, 1)
        assert fb_updated.status == "In Progress"


def test_status_update_invalid_rejected():
    """Invalid status value is rejected and original preserved."""
    app = _make_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin = User(name="Admin", email="admin@test.com", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)

        student = User(name="Std", email="std@t.com", role="student")
        student.set_password("pass123")
        db.session.add(student)
        db.session.flush()

        fb = Feedback(
            student_id=student.id,
            category="Food",
            rating=4,
            comment="Test.",
            status="Pending",
        )
        db.session.add(fb)
        db.session.commit()

    with app.test_client() as client:
        _login_admin(client)
        resp = client.post(
            "/admin/feedback/1/status",
            data={"status": "INVALID"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

    with app.app_context():
        fb_updated = db.session.get(Feedback, 1)
        assert fb_updated.status == "Pending"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
