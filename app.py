"""Application factory for the Student Feedback Management System."""

from flask import Flask


def create_app(config_object=None):
    """Create and configure the Flask application.

    Parameters
    ----------
    config_object : str or type, optional
        Configuration class (e.g., ``DevelopmentConfig``).  Falls back to
        the base ``Config`` when *None*.
    """

    app = Flask(__name__)

    from config import Config as _Config

    if config_object is not None:
        if isinstance(config_object, str):
            app.config.from_object(config_object)
        else:
            app.config.from_object(config_object)
    else:
        # Default: load base Config (reads DATABASE_URL / SECRET_KEY from env)
        app.config.from_object(_Config)

    # Initialise extensions (deferred binding — no app context yet)
    from models import db
    db.init_app(app)

    # Register blueprints — routes are added in subsequent steps.
    # See PROJECT.md → Routes for the expected URL layout.
    from blueprints.auth import auth_bp
    from blueprints.student import student_bp
    from blueprints.admin import admin_bp
    from blueprints.faculty import faculty_bp

    app.register_blueprint(auth_bp)          # /register, /login, /logout
    app.register_blueprint(student_bp)       # /dashboard (student)
    app.register_blueprint(
        admin_bp, url_prefix="/admin"        # /admin/dashboard, /admin/feedback/<id>
    )                                         # Note: /reports is at root — see PROJECT.md
    app.register_blueprint(
        faculty_bp, url_prefix="/faculty"    # /faculty/dashboard, etc.
    )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
