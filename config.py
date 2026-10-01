"""Configuration classes for the Student Feedback Management System."""

import os

# Determine database URI: explicit env var overrides default SQLite
# Absolute path for SQLite so it works regardless of CWD
_instance_dir = os.path.join(os.path.dirname(__file__), "instance")
os.makedirs(_instance_dir, exist_ok=True)
_default_db = (
    os.environ.get("DATABASE_URL")
    or f"sqlite:///{os.path.join(_instance_dir, 'student_feedback.db')}"
)


class Config:
    """Base configuration — overrides live in subclasses."""

    SECRET_KEY = os.environ.get(
        "SECRET_KEY", "dev-secret-key-change-in-prod"
    )
    SQLALCHEMY_DATABASE_URI = _default_db
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
