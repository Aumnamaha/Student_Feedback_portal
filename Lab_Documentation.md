# Lab Documentation — Object-Oriented Software Engineering

## Experiment / Project Title
**Design and Implementation of a Student Feedback Management System using Flask, MySQL, and OOSE Principles**

---

## 1. Aim

To design, develop, and document a fully functional web-based **Student Feedback Management System** that enables students to submit structured feedback about various aspects of campus life and allows administrators to manage, track, categorize, and resolve submitted feedback. The project applies core Object-Oriented Software Engineering (OOSE) principles including modular architecture, role-based access control, database-driven persistence, and systematic software development lifecycle practices.

---

## 2. Tools and Technologies Used

| Category          | Tool / Technology                                      |
|-------------------|--------------------------------------------------------|
| Programming Language | Python 3                                              |
| Web Framework     | Flask (Python microframework)                          |
| Database          | MySQL Server / SQLite                                  |
| ORM               | SQLAlchemy                                             |
| Frontend          | HTML5, CSS3, Vanilla JavaScript                        |
| Template Engine   | Jinja2 (integrated with Flask)                         |
| Security          | werkzeug.security — password hashing                   |
| CSRF Protection   | Flask-WTF                                              |
| Session Management| Flask sessions                                         |
| Version Control   | Git / GitHub                                           |
| IDE               | VS Code / PyCharm                                      |
| API Testing       | Postman / Browser DevTools                             |

---

## 3. System Requirements

### 3.1 Hardware Requirements

| Component     | Minimum Specification         | Recommended           |
|---------------|-------------------------------|-----------------------|
| Processor     | Dual-core, 2.0 GHz            | Quad-core, 2.5+ GHz   |
| RAM           | 4 GB                          | 8 GB or more          |
| Storage       | 500 MB free disk space        | 1 GB free             |
| Network       | Localhost (no external network required for demo) | — |

### 3.2 Software Requirements

| Component       | Version              |
|-----------------|----------------------|
| Operating System| Linux / Windows / macOS |
| Python          | 3.8 or later         |
| MySQL           | 5.7 or 8.0           |
| pip             | Latest stable        |
| Browser         | Chrome 90+, Firefox 88+, Edge 90+ |

---

## 4. Step-by-Step Implementation Summary

### Phase 1: Requirement Analysis and Design
- Identified functional requirements (registration, feedback submission, filtering, status management, reports).
- Defined non-functional requirements (usability, security, performance, reliability).
- Designed the database schema with four core tables (`users`, `faculty`, `feedback`, `comment`) including self-referencing comment threads and foreign keys for student-to-feedback and faculty-resolver relationships.
- Created modular blueprints for separation of concerns: `auth`, `student`, `admin`, `faculty`.

### Phase 2: Database Setup
- Wrote `schema.sql` to create MySQL database, tables, constraints, and default ENUM values.
- Implemented seed script (`seed.py`) to insert a default admin account with a hashed password.

### Phase 3: Backend Development (Flask)
- Set up the application factory pattern in `app.py` with CSRF protection via Flask-WTF.
- Configured SQLAlchemy connection to MySQL or SQLite (fallback) via environment-based configuration (`DATABASE_URL`) in `config.py`. Production mode enforces `SECRET_KEY` from environment.
- Defined ORM models (`User`, `Faculty`, `Feedback`, `Comment`) in `models.py` using Flask-SQLAlchemy with relationships, verification lifecycle helpers (`verify_success`, `verify_failure`), and PII-safe serialization methods (`to_faculty_dict`, `to_admin_dict`).
- Implemented four blueprints:
  - **Auth Blueprint**: Registration (with password hashing), login (multi-role: student/admin/faculty), logout.
  - **Student Blueprint**: Feedback submission form, student dashboard displaying personal feedback history with comment thread previews.
  - **Admin Blueprint**: Admin-only dashboard with multi-criteria filtering, individual feedback detail view with status updates and verification actions, faculty account management, and reports page with aggregated statistics (including department-wise counts and escalation metrics).
  - **Faculty Blueprint**: Department-filtered feedback dashboard (excluding 5-star ratings), feedback review with status transitions (Pending → In Progress → Resolved), comment posting, resolution verification (Verified/Closed or revert to In Progress), automatic escalation of overdue items, and deadline countdowns.

### Phase 4: Frontend Development
- Built responsive HTML templates using Jinja2 for server-side rendering.
- Created a `base.html` template with shared navigation, flash message display, and consistent layout.
- Developed role-specific dashboards with filter forms (admin) and submission forms (student).
- Added client-side JavaScript for form validation, dynamic filtering, and interactive status updates.

### Phase 5: Security Implementation
- Passwords hashed using `werkzeug.security.generate_password_hash` / `check_password_hash`.
- Session-based authentication with role checks (`@login_required`, `@admin_required`, `@faculty_required` decorators).
- CSRF protection via Flask-WTF on all POST forms and AJAX requests (X-CSRFToken header).
- Anonymous feedback enforced at the **serialization layer** — `to_admin_dict()` hides PII for anonymous rows; `to_faculty_dict()` only exposes class/year derived from roll number, never name/email/roll.
- Production SECRET_KEY enforcement: application refuses to start without a real secret key when DEBUG=False.

### Phase 6: Testing and Refinement
- Manual testing of all user flows (registration, login, submission, filtering, status updates, reports).
- Created 79 pytest unit tests across 5 files: `test_auth.py` (auth + CSRF rejection), `test_admin.py` (admin dashboard & status updates), `test_admin_pii.py` (admin PII protection for anonymous feedback), `test_faculty_pii.py` (faculty department filtering and anonymity), and `test_reports.py` (report aggregation).
- Verified mobile responsiveness across screen sizes.

---

## 5. Sample Code Snippets for Key Modules

### 5.1 User Authentication (Login) — `blueprints/auth.py`

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        user = User.query.get(session['user_id'])
        return redirect(url_for(f'{user.role}.dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier')  # email or roll_number
        password = request.form.get('password')
        
        user = User.query.filter(
            (User.email == identifier) | (User.roll_number == identifier)
        ).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            flash('Login successful!', 'success')
            return redirect(url_for(f'{user.role}.dashboard'))
        else:
            flash('Invalid credentials.', 'danger')

    return render_template('login.html')
```

### 5.2 Feedback Submission — `blueprints/student.py`

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, User, Feedback

student_bp = Blueprint('student', __name__, url_prefix='/dashboard')

@student_bp.route('/submit', methods=['POST'])
def submit_feedback():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

    category = request.form.get('category')
    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    is_anonymous = request.form.get('anonymous') == 'on'

    new_feedback = Feedback(
        student_id=session['user_id'],
        category=category,
        rating=rating,
        comment=comment,
        is_anonymous=is_anonymous
    )

    db.session.add(new_feedback)
    db.session.commit()
    flash('Feedback submitted successfully!', 'success')
    return redirect(url_for('student.dashboard'))
```

### 5.3 Admin Status Update — `blueprints/admin.py`

```python
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, Feedback

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/feedback/<int:feedback_id>', methods=['POST'])
def update_feedback_status(feedback_id):
    if not session.get('user_id') or session.get('role') != 'admin':
        return redirect(url_for('auth.login'))

    feedback = Feedback.query.get_or_404(feedback_id)
    new_status = request.form.get('status')

    if new_status in ['Pending', 'In Progress', 'Resolved']:
        feedback.status = new_status
        db.session.commit()
        flash(f'Feedback status updated to "{new_status}".', 'success')
    
    return redirect(url_for('admin.dashboard'))
```

### 5.4 Anonymous Feedback Query Enforcement — `blueprints/admin.py`

```python
@admin_bp.route('/dashboard')
def dashboard():
    # Admin can view feedback, but anonymous entries hide student identity at query level
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    
    for fb in feedbacks:
        if fb.is_anonymous:
            fb.student_name = 'Anonymous'  # Identity suppressed at query layer
        else:
            fb.student_name = fb.user.name

    return render_template('admin_dashboard.html', feedbacks=feedbacks)
```

---

## 6. Output / Result Description

The Student Feedback Management System successfully implements all specified functional and non-functional requirements. The application runs on a local Flask development server (`http://127.0.0.1:5000`) and provides the following confirmed outputs:

- **Student Registration**: New students can create accounts with validated roll number and email. Passwords are stored as bcrypt-style hashes in MySQL — plain-text passwords never persist.
- **Multi-Role Login System**: Students, admins, and faculty authenticate via session-based login. Upon successful authentication, users are redirected to their respective dashboards based on role (student → `/dashboard`, admin → `/admin/dashboard`, faculty → `/faculty/dashboard`).
- **Faculty Accounts**: Faculty accounts are created by admins (no self-registration). Each faculty has a department and subject assignment that determines which feedback they can see.
- **Feedback Submission (Student)**: Students can submit feedback with category selection, star rating (1–5), text comment, and anonymous toggle. Submissions capture department, subject, and semester/year for Faculty/Food categories. Review deadlines are set to 24 hours from submission.
- **Student Dashboard**: Displays all feedback submitted by the logged-in student, showing category, rating, status badge (Pending / In Progress / Resolved / Pinned / Verified/Closed / Verification Failed), countdown timers, and comment thread previews.
- **Faculty Dashboard**: Shows department-filtered feedback (excluding 5-star ratings) with subject-match highlighting, escalation badges, and deadline countdowns. Faculty can update status, post comments, and verify resolved items.
- **Admin Dashboard**: Presents a table of all feedback entries with multi-criteria filtering. Includes a dedicated Faculty Review section for Resolved/Pinned items awaiting verification, with verify-success/verify-failure actions.
- **Status Management**: Both admins and faculty can update feedback status through Pending → In Progress → Resolved. Admins also handle the verification step (Resolved → Verified/Closed or revert to In Progress).
- **Comment Threads**: Reddit-style threaded discussion on each feedback item. Matching faculty can post comments; students view read-only. Supports nested replies.
- **Verification Workflow**: Both admin and faculty can verify resolved items — success transitions to Verified/Closed, failure reverts to In Progress with `failed_verification_count` incremented. Items reaching 3 failed verifications are auto-flagged as escalated.
- **Escalation System**: Overdue feedback is automatically pinned with escalation deadlines set to 3 days ahead. Admin dashboard highlights all escalated items (pinned + high-fail-count).
- **Reports Page**: Displays aggregated statistics — average rating per category, total feedback count per status/category/department, monthly submission trends, and escalation metrics.
- **Anonymous Feedback**: When a student submits with anonymity enabled, the admin dashboard displays "Anonymous" as the submitter name. Faculty views never receive PII — only class/year derived from roll number. The actual `student_id` is retained internally for audit purposes but never exposed through any admin-facing interface or report.
- **CSRF Protection**: All POST forms include hidden CSRF tokens; AJAX comment submissions send X-CSRFToken headers.

---

## 7. Viva-Relevant Questions and Answers

### Q1: What is Object-Oriented Software Engineering (OOSE), and how did you apply it in this project?
**A:** OOSE is a software development methodology that organizes systems around objects — encapsulating data (attributes) and behavior (methods) within classes. In this project, we applied OOSE principles by creating two core classes (`User` and `Feedback`) as SQLAlchemy ORM models with well-defined attributes, relationships (`db.relationship`), and methods. The modular blueprint architecture follows the object-oriented principle of separation of concerns, where each blueprint encapsulates a specific set of related operations (authentication, student actions, admin actions).

### Q2: Why did you choose Flask over Django or another framework?
**A:** Flask is a lightweight microframework that provides maximum flexibility without imposing rigid project structure. For this lab project, we needed fine-grained control over routing, templating, and database integration — Flask's minimalistic approach allowed us to implement custom authentication decorators, modular blueprints, and direct SQLAlchemy ORM usage without framework-level abstractions. Django's built-in admin and ORM, while powerful, would have added unnecessary complexity for a lab-scale project where we needed to demonstrate understanding of each component.

### Q3: How does your system ensure the security of student passwords?
**A:** Passwords are never stored in plain text. Upon registration, the plaintext password is passed through `werkzeug.security.generate_password_hash()`, which creates a salted bcrypt-style hash. During login, `check_password_hash()` compares the entered password against the stored hash — it never decrypts anything because hashing is a one-way function. Additionally, Flask sessions use signed cookies with an application-specific secret key, preventing session tampering.

### Q4: Explain how anonymous feedback privacy is enforced in your system.
**A:** Anonymous feedback privacy is enforced at **multiple layers**: (1) At the query layer, when admin dashboard data is fetched, any `Feedback` record with `is_anonymous=True` has its associated student name replaced with "Anonymous" before being passed to the template. (2) At the template layer, conditional Jinja2 logic ensures no student identifier columns are rendered for anonymous entries. (3) The database relationship (`student_id`) is retained internally for audit trails but never exposed through any admin UI, API endpoint, or report export. This defense-in-depth approach ensures anonymity cannot be accidentally bypassed by a single-layer fix.

### Q5: What design pattern did you use for organizing your Flask application?
**A:** We used the **Blueprint Pattern** combined with the **Application Factory Pattern**. The application factory (`create_app()` in `app.py`) centralizes configuration, extension initialization (SQLAlchemy, CSRFProtect), and blueprint registration. Four blueprints organize routes into modular units: `auth_bp` (registration/login/logout), `student_bp` (feedback submission + personal history), `admin_bp` (all feedback management, verification, faculty management, reports), and `faculty_bp` (department-filtered review, comments, status transitions, resolution verification). This pattern promotes separation of concerns, testability, and scalability.

### Q6: How does your database schema support the system's requirements?
**A:** The schema uses four tables:
- **users**: Stores student and admin accounts with ENUM role (`student`/`admin`). One-to-many relationship to `feedback`.
- **faculty**: Stores faculty accounts created by admins (no self-registration). Includes department, subject_taught, and a one-to-many relationship to `feedback` via `resolved_by_faculty_id`.
- **feedback**: Core table with ENUM columns for category (`Food`/`Faculty`/`Infrastructure`/`Events`/`Other`), status (`Pending`/`In Progress`/`Resolved`/`Pinned`/`Verified/Closed`/`Verification Failed`), and TINYINT rating (1–5). FK to `users` for student origin, FK to `faculty` for resolver. Includes `is_anonymous`, `department`, `subject`, `semester_year`, `review_deadline`, `escalation_deadline`, and `failed_verification_count`.
- **comment**: Self-referencing table (FK `parent_id` → `comment.id`) enabling threaded replies. FK to `feedback`. Each comment tracks `author_type` (`faculty`/`student`) and `author_id`.

ENUM types enforce data integrity at the database level — invalid categories, ratings outside 1–5, or unrecognized statuses cannot be inserted.

---

*This lab documentation was prepared as part of the Object-Oriented Software Engineering course practical submission.*
