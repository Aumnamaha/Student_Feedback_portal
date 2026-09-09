"""Seed script — creates an initial admin account if none exists."""

import os

from app import create_app, db


def seed_admin():
    """Create a default admin user for development/demo use."""
    from models import User

    app = create_app()

    with app.app_context():
        # Ensure tables exist
        db.create_all()

        existing = User.query.filter_by(role='admin').first()
        if existing:
            print(f"Admin account already exists: {existing.email}")
            return

        admin = User(
            name='System Admin',
            email='admin@studentfeedback.local',
            password_hash='',  # will be set below
            role='admin',
        )
        admin.set_password('admin123')  # change in production!
        db.session.add(admin)
        db.session.commit()

        print("Admin account created:")
        print(f"  Email:    {admin.email}")
        print(f"  Password: admin123")


if __name__ == '__main__':
    seed_admin()
