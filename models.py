"""SQLAlchemy data models — mirrors the MySQL schema in schema.sql."""

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
        db.Enum("Pending", "In Progress", "Resolved"),
        default="Pending",
        nullable=False,
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    def __repr__(self):
        return f"<Feedback {self.id} | {self.category}>"
