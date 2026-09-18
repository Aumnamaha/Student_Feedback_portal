"""Seed script — creates initial admin and faculty accounts."""

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


def seed_faculty(name, email, faculty_id, department, subject_taught,
                 password):
    """Create a single faculty account (admin-seeded only).

    Parameters
    ----------
    name : str
        Full name of the faculty member.
    email : str
        Unique email address.
    faculty_id : str
        Unique institutional identifier (e.g., emp ID).
    department : str
        Department name.
    subject_taught : str
        Subject(s) taught by this faculty.
    password : str
        Plain-text password (will be hashed before storage).

    Returns
    -------
    Faculty or None — the created Faculty object, or ``None`` if one
    with the same email/faculty_id already exists.
    """
    from models import Faculty

    app = create_app()

    with app.app_context():
        db.create_all()

        # Check for existing faculty by email or faculty_id
        existing_by_email = Faculty.query.filter_by(email=email).first()
        if existing_by_email:
            print(f"Faculty account already exists: {email}")
            return None

        existing_by_id = Faculty.query.filter_by(
            faculty_id=faculty_id
        ).first()
        if existing_by_id:
            print(
                f"Faculty with ID '{faculty_id}' already exists "
                f"(email: {existing_by_id.email})"
            )
            return None

        faculty = Faculty(
            name=name,
            email=email,
            faculty_id=faculty_id,
            department=department,
            subject_taught=subject_taught,
            password_hash='',
        )
        faculty.set_password(password)
        db.session.add(faculty)
        db.session.commit()

        print("Faculty account created:")
        print(f"  Name:       {faculty.name}")
        print(f"  Email:      {faculty.email}")
        print(f"  Faculty ID: {faculty.faculty_id}")
        print(f"  Department: {faculty.department}")
        print(f"  Subject(s): {faculty.subject_taught}")
        print(f"  Password:   {password}")

        return faculty


def seed_sample_faculty():
    """Create a couple of sample faculty accounts for demo use."""
    seed_faculty(
        name='Dr. Priya Sharma',
        email='priya.sharma@studentfeedback.local',
        faculty_id='FAC-001',
        department='Computer Science',
        subject_taught='Data Structures, Algorithms',
        password='faculty123',
    )
    seed_faculty(
        name='Prof. Rajesh Kumar',
        email='rajesh.kumar@studentfeedback.local',
        faculty_id='FAC-002',
        department='Electronics',
        subject_taught='Circuits, Signal Processing',
        password='faculty123',
    )


if __name__ == '__main__':
    seed_admin()
    seed_sample_faculty()
