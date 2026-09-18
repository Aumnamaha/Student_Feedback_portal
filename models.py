"""SQLAlchemy data models — mirrors the MySQL schema in schema.sql."""

from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.types import TypeDecorator, Integer

db = SQLAlchemy()


class TinyInt(TypeDecorator):
    """Portable TINYINT that maps to SMALLINT on non-MySQL backends.

    On MySQL it renders as ``TINYINT`` (matching schema.sql exactly).
    On SQLite/PostgreSQL it falls back to ``SMALLINT`` so tests work.
    """
    impl = Integer
    cache_ok = True

    def __init__(self):
        super().__init__()

    @property
    def python_type(self):
        return int

    def process_literal_param(self, value, dialect):
        if dialect.name == 'mysql':
            return int(value)
        return value

    def get_dbapi_type(self, dbapi):
        return int


class User(db.Model):
    """User accounts — students and admins."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    roll_number = db.Column(db.String(50), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("student", "admin"),
        nullable=False,
        default="student",
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    feedback_submitted = db.relationship(
        "Feedback", backref="author", lazy="dynamic"
    )

    # --- password helpers (werkzeug) ---

    def set_password(self, raw_password: str) -> None:
        """Hash *raw_password* and store it in ``password_hash``."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Return ``True`` if *raw_password* matches the stored hash."""
        return check_password_hash(self.password_hash, raw_password)


class Faculty(db.Model):
    """Faculty accounts — admin-seeded only (no self-registration)."""

    __tablename__ = "faculty"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    faculty_id = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    subject_taught = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum("faculty"),
        nullable=False,
        default="faculty",
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    feedback_resolved = db.relationship(
        "Feedback", backref="resolver", lazy="dynamic",
        foreign_keys="Feedback.resolved_by_faculty_id"
    )

    # --- password helpers (werkzeug) ---

    def set_password(self, raw_password: str) -> None:
        """Hash *raw_password* and store it in ``password_hash``."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Return ``True`` if *raw_password* matches the stored hash."""
        return check_password_hash(self.password_hash, raw_password)


class Feedback(db.Model):
    """Individual feedback entries submitted by students."""

    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    category = db.Column(
        db.Enum("Food", "Faculty", "Infrastructure", "Events", "Other"),
        nullable=False,
    )
    rating = db.Column(TinyInt(), nullable=False)
    comment = db.Column(db.Text, nullable=False)
    is_anonymous = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(
        db.Enum("Pending", "In Progress", "Resolved",
                "Verified/Closed", "Verification Failed"),
        default="Pending",
        nullable=False,
    )
    department = db.Column(db.String(100), nullable=True)
    subject = db.Column(db.String(200), nullable=True)
    semester_year = db.Column(db.String(20), nullable=True)
    resolved_by_faculty_id = db.Column(
        db.Integer, db.ForeignKey("faculty.id"), nullable=True
    )
    review_deadline = db.Column(db.DateTime, nullable=True)
    escalation_deadline = db.Column(db.DateTime, nullable=True)
    failed_verification_count = db.Column(
        TinyInt(), nullable=False, default=0
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"<Feedback {self.id} | {self.category}>"

    # ------------------------------------------------------------------
    #  VERIFICATION LIFECYCLE HELPERS
    # ------------------------------------------------------------------

    def verify_success(self) -> None:
        """Transition from 'Resolved' → 'Verified/Closed'."""
        if self.status != "Resolved":
            raise ValueError(
                f"Cannot verify feedback with status '{self.status}'. "
                "Must be 'Resolved'."
            )
        self.status = "Verified/Closed"

    def verify_failure(self) -> None:
        """Transition from 'Resolved' → 'In Progress', increment counter."""
        if self.status != "Resolved":
            raise ValueError(
                f"Cannot fail-verify feedback with status '{self.status}'. "
                "Must be 'Resolved'."
            )
        self.failed_verification_count = (
            (self.failed_verification_count or 0) + 1
        )
        self.status = "In Progress"

    # ------------------------------------------------------------------
    #  ADMIN-FACING SERIALIZATION — enforces anonymous PII protection
    # ------------------------------------------------------------------

    def to_admin_dict(self) -> dict:
        """Return a dict representation safe for admin-facing views.

        **Security**: student PII is *never* returned for anonymous rows,
        even if ``self.author`` is loaded.  Callers should also avoid
        joining the users table for anonymous feedback at the query level.

        Returns raw datetime objects so templates can format them with
        ``strftime()`` — ISO strings are not used here to keep formatting
        flexible across different views.
        """
        result = {
            "id": self.id,
            "category": self.category,
            "rating": int(self.rating),
            "comment": self.comment,
            "is_anonymous": bool(self.is_anonymous),
            "status": self.status,
            # Raw datetime — templates call .strftime() on these
            "created_at": self.created_at,
        }

        # Only attach student PII when NOT anonymous
        if not self.is_anonymous and self.author is not None:
            result["student_name"] = self.author.name
            result["student_email"] = self.author.email
            result["student_roll_number"] = self.author.roll_number
        else:
            # Anonymous or author not loaded — hide PII completely
            result["student_name"] = "Anonymous"
            result["student_email"] = None
            result["student_roll_number"] = None

        return result

    # ------------------------------------------------------------------
    #  QUERY HELPERS — query-level anonymity for admin views
    # ------------------------------------------------------------------

    @staticmethod
    def admin_query(session, category=None, rating=None, status=None,
                    date_from=None, date_to=None, keyword=None):
        """Build an admin-safe feedback query.

        Returns a ``Query`` object that can be further filtered/paginated.
        For anonymous rows the ``author`` relationship is NOT eagerly loaded
        (avoiding unnecessary DB joins).  PII protection is enforced at the
        serialization level via :meth:`to_admin_dict`.

        Parameters
        ----------
        session : SQLAlchemy session
            Active database session.
        category, rating, status : str or int, optional
            Filter by exact match.
        date_from, date_to : datetime, optional
            Inclusive date range on ``created_at``.
        keyword : str, optional
            Case-insensitive substring search in comments.

        Returns
        -------
        sqlalchemy.orm.Query
        """
        q = session.query(Feedback)

        if category:
            q = q.filter(Feedback.category == category)
        if rating is not None:
            q = q.filter(Feedback.rating == int(rating))
        if status:
            q = q.filter(Feedback.status == status)
        if date_from:
            from datetime import datetime as _dt
            target = _dt.fromisoformat(date_from) if isinstance(date_from, str) else date_from
            q = q.filter(Feedback.created_at >= target)
        if date_to:
            from datetime import datetime as _dt
            end = _dt.fromisoformat(date_to) if isinstance(date_to, str) else date_to
            end = end.replace(hour=23, minute=59, second=59)
            q = q.filter(Feedback.created_at <= end)
        if keyword:
            q = q.filter(Feedback.comment.ilike(f"%{keyword}%"))

        return q.order_by(Feedback.created_at.desc())


# ------------------------------------------------------------------
#  HELPER — get current user from session (used by route decorators)
# ------------------------------------------------------------------

from flask import session as _flask_session

def current_user():
    """Return the currently logged-in User object, or ``None``."""
    if 'user_id' not in _flask_session:
        return None
    return db.session.get(User, _flask_session['user_id'])


def current_faculty():
    """Return the currently logged-in Faculty object, or ``None``."""
    if 'faculty_id' not in _flask_session:
        return None
    return db.session.get(Faculty, _flask_session['faculty_id'])
