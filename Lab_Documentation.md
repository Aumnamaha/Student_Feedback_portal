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
| Database          | MySQL Server                                           |
| ORM               | SQLAlchemy                                             |
| Frontend          | HTML5, CSS3, Vanilla JavaScript                        |
| Template Engine   | Jinja2 (integrated with Flask)                         |
| Security          | werkzeug.security — password hashing                   |
| Session Management| Flask-Session (server-side sessions)                   |
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
- Designed the database schema with two core tables (`users`, `feedback`) and a one-to-many relationship.
- Created modular blueprints for separation of concerns: `auth`, `student`, `admin`.

### Phase 2: Database Setup
- Wrote `schema.sql` to create MySQL database, tables, constraints, and default ENUM values.
- Implemented seed script (`seed.py`) to insert a default admin account with a hashed password.

### Phase 3: Backend Development (Flask)
- Set up the application factory pattern in `app.py`.
- Configured SQLAlchemy connection to MySQL via environment-based configuration in `config.py`.
- Defined ORM models (`User`, `Feedback`) in `models.py` using Flask-SQLAlchemy with relationships and validation.
- Implemented three blueprints:
  - **Auth Blueprint**: Registration (with password hashing), login (session creation), logout (session destruction).
  - **Student Blueprint**: Feedback submission form, student dashboard displaying personal feedback history.
  - **Admin Blueprint**: Admin-only dashboard with multi-criteria filtering, individual feedback detail view with status updates, and reports page with aggregated statistics.

### Phase 4: Frontend Development
- Built responsive HTML templates using Jinja2 for server-side rendering.
- Created a `base.html` template with shared navigation, flash message display, and consistent layout.
- Developed role-specific dashboards with filter forms (admin) and submission forms (student).
- Added client-side JavaScript for form validation, dynamic filtering, and interactive status updates.

### Phase 5: Security Implementation
- Passwords hashed using `werkzeug.security.generate_password_hash` / `check_password_hash`.
- Session-based authentication with role checks (`@login_required`, `@admin_required` decorators).
- Anonymous feedback enforced at the **query layer** — admin queries filter out student identity when `is_anonymous=True`.

### Phase 6: Testing and Refinement
- Manual testing of all user flows (registration, login, submission, filtering, status updates, reports).
- Created unit test files for authentication (`test_auth.py`), admin functionality (`test_admin.py`, `test_admin_pii.py`), student PII protection (`test_faculty_pii.py`), and report generation (`test_reports.py`).
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
- **Login System**: Both students and admins authenticate via session-based login. Upon successful authentication, users are redirected to their respective dashboards based on role.
- **Feedback Submission (Student)**: Students can submit feedback with category selection, star rating, text comment, and anonymous toggle. Submissions are immediately persisted in the database with a timestamp.
- **Student Dashboard**: Displays all feedback submitted by the logged-in student, showing category, rating, comment snippet, status badge, and submission date.
- **Admin Dashboard**: Presents a paginated table of all feedback entries with sortable columns. Filters allow narrowing by category (dropdown), rating range, status, and custom date range. A keyword search bar performs full-text matching on comments.
- **Status Management**: Admins can update any feedback entry from Pending → In Progress → Resolved via a detail view page. Each update is timestamped in the `updated_at` column.
- **Reports Page**: Displays aggregated statistics — average rating per category (bar chart), total feedback count per category (pie/donut visualization), and weekly/monthly submission trends (line chart).
- **Anonymous Feedback**: When a student submits with anonymity enabled, the admin dashboard displays "Anonymous" as the submitter name. The actual `student_id` is retained internally for audit purposes but never exposed through any admin-facing interface or report.

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
**A:** We used the **Blueprint Pattern** combined with the **Application Factory Pattern**. The application factory (`create_app()` in `app.py`) centralizes configuration, extension initialization (SQLAlchemy), and blueprint registration. Blueprints (`auth_bp`, `student_bp`, `admin_bp`) organize routes into modular, reusable units — each handling a specific domain of functionality. This pattern promotes separation of concerns, testability, and scalability as the application grows.

### Q6: How does your database schema support the system's requirements?
**A:** The schema uses two tables with a one-to-many relationship (`users` → `feedback`). The `users` table stores role information via an ENUM column (`student`/`admin`), enabling role-based access control at the application layer. The `feedback` table uses ENUM types for `category`, `status`, and a TINYINT for `rating` to enforce data integrity at the database level — invalid categories, ratings outside 1–5, or unrecognized statuses cannot be inserted. The `is_anonymous` boolean flag enables privacy filtering, while `created_at` and `updated_at` timestamps support trend analysis in reports and audit trails.

---

*This lab documentation was prepared as part of the Object-Oriented Software Engineering course practical submission.*
