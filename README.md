# Student Feedback Management System

A web-based application for students to submit structured feedback about campus life (food, faculty, infrastructure, events, etc.) and for administrators to view, categorize, track, and resolve that feedback. Built as an Object-Oriented Software Engineering (OOSE) lab project.

---

## Features

- **Student Registration & Login** — Students register using roll number/email and password; secure session-based authentication with hashed passwords.
- **Faculty Login** — Faculty members log in with email/password to review department-specific feedback. No self-registration for faculty (accounts are created by admins).
- **Admin Login** — Admins log in with seeded credentials to manage all feedback and faculty accounts.
- **Feedback Submission** — Submit feedback categorized into Food, Faculty, Infrastructure, Events, or Other, with a 1–5 star rating and optional text comment. Toggle anonymous submission. Department and subject are captured for Faculty/Food categories.
- **Student Dashboard** — View personal feedback history with current status (Pending / In Progress / Resolved / Pinned / Verified/Closed / Verification Failed).
- **Faculty Dashboard** — View department-filtered feedback (excluding 5-star ratings), update status through the workflow, post comments, and verify resolved items.
- **Admin Dashboard** — View all student feedback in an organized table with multi-criteria filtering (category, rating, status, date range) and keyword search. Dedicated Faculty Review section for Resolved/Pinned items awaiting verification.
- **Feedback Management** — Admins can update feedback status through the workflow: Pending → In Progress → Resolved. Faculty can also transition their assigned department's feedback through this pipeline.
- **Comment Threads** — Reddit-style threaded comments on feedback items. Matching faculty can post; students view read-only. Supports nested replies via self-referencing parent_id.
- **Verification Workflow** — Both admin and faculty can verify resolved feedback: success marks it Verified/Closed, failure reverts to In Progress and increments the failed verification counter. After 3 failed verifications, items escalate.
- **Escalation System** — Overdue feedback is automatically pinned with escalation deadlines. Items with `failed_verification_count >= 3` are flagged as escalated. Admin dashboard highlights all escalated items.
- **Reports & Analytics** — Visual summary of average ratings per category, feedback volume trends over time, categorical breakdowns, department-wise counts, and verification metrics.
- **Anonymous Feedback** — Student identity is hidden from all admin-facing views when anonymous mode is enabled (enforced at the serialization layer). Faculty views never receive PII — only class/year derived from roll number.
- **CSRF Protection** — All POST forms include CSRF tokens; AJAX comment submissions send `X-CSRFToken` headers via Flask-WTF.
- **Role-Based Access Control** — Strict separation between student, admin, and faculty privileges with decorator-based access guards.

---

## Tech Stack

| Layer        | Technology                        |
|-------------|-----------------------------------|
| Frontend    | HTML5, CSS3, Vanilla JavaScript   |
| Backend     | Python 3 · Flask (microframework) |
| Database    | MySQL / SQLite (fallback)         |
| ORM         | SQLAlchemy                        |
| Security    | werkzeug.security (password hashing), Flask-WTF (CSRF), Flask sessions |

---

## Folder Structure

```
Student_Feedback/
├── app.py                  # Application factory & entry point
├── config.py               # Configuration settings (DB URI, secret key)
├── models.py               # SQLAlchemy ORM models: User, Faculty, Feedback, Comment
├── schema.sql              # Raw MySQL schema for database creation
├── seed.py                 # Seed script to create admin account(s)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template (copy to .env)
├── README.md               # This file
│
├── blueprints/             # Modular Flask route blueprints
│   ├── auth/               # Registration, login, logout routes
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── student/            # Student dashboard & feedback submission
│   │   └── __init__.py
│   ├── admin/              # Admin dashboard, filters, status updates, reports, faculty management
│   │   └── __init__.py
│   └── faculty/            # Faculty dashboard, review, comments, verification
│       ├── __init__.py
│       └── routes.py
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Base layout with navigation & CSRF meta tag
│   ├── login.html          # Multi-role login (student/admin/faculty)
│   ├── register.html       # Student registration
│   ├── student_dashboard.html  # Submit feedback + view history + read-only comments
│   ├── faculty_dashboard.html    # Department feedback table with stats
│   ├── faculty_feedback_detail.html # Review, comment, status update, verify
│   ├── admin_dashboard.html        # All feedback + Faculty Review section
│   ├── admin_feedback_detail.html  # View/update status, verify resolved items
│   ├── admin_faculty.html          # List and create faculty accounts
│   └── reports.html                # Aggregate analytics & trends
│
├── static/                 # Static assets
│   ├── css/style.css
│   └── js/
│       ├── main.js
│       ├── countdown.js    # Deadline countdown timers
│       └── comments.js     # AJAX comment loading/posting with CSRF
│
├── instance/               # SQLite fallback / runtime data (git-ignored)
│   └── student_feedback.db
│
├── test_auth.py            # Auth + CSRF tests
├── test_admin.py           # Admin dashboard & status update tests
├── test_admin_pii.py       # Admin PII protection tests
├── test_faculty_pii.py     # Faculty anonymity / department filter tests
└── test_reports.py         # Reports aggregation tests
```

---

## Installation & Setup

### Prerequisites

- Python 3.8 or later
- pip (Python package manager)
- MySQL Server 5.7+ / 8.0+ (optional — SQLite is the fallback for development/testing)

### Step 1 — Clone the Repository

```bash
git clone https://github.com/Aumnamaha/Student_Feedback_portal.git
cd Student_Feedback
```

### Step 2 — Set Up Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:

- `SECRET_KEY` — A strong random secret key for session signing (required in production). Generate one with:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `DATABASE_URL` — Database connection string. Examples:
  - **SQLite** (default, no setup needed): leave unset or use `sqlite:///instance/student_feedback.db`
  - **MySQL**: `mysql+pymysql://user:password@localhost/student_feedback`

### Step 3 — Create the MySQL Database (if using MySQL)

```sql
CREATE DATABASE student_feedback CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE student_feedback;
SOURCE schema.sql;   -- or execute schema.sql contents in your MySQL client
```

### Step 4 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Seed an Admin Account

```bash
python seed.py
```

This creates the default admin user. Student accounts are self-registered through `/register`. Faculty accounts are created by admins via the "Manage Faculty" page in the admin dashboard (or seeded programmatically).

### Step 6 — Run the Application

```bash
python app.py
```

The server will start on `http://127.0.0.1:5000` (or another port if configured).

---

## Usage

### For Students

1. Navigate to `/register` and create an account using your roll number and email.
2. Log in at `/login`.
3. On the student dashboard, submit feedback by selecting a category, rating (1–5), writing a comment, and optionally toggling anonymous mode.
4. View your submitted feedback and track its resolution status through Pending → In Progress → Resolved → Verified/Closed or Verification Failed.
5. Click "View Comments" on any feedback item to read the discussion thread posted by faculty.

### For Administrators

1. Log in with admin credentials (seeded via `seed.py`).
2. Access the admin dashboard to view all student feedback with filter controls and keyword search.
3. Use filters (category, rating, status, date range) and keyword search to narrow results.
4. Click on a feedback entry to update its status: Pending → In Progress → Resolved.
5. Visit the Faculty Review section for Resolved items awaiting verification — mark them Verified/Closed or fail verification (reverts to In Progress).
6. Manage faculty accounts via "Manage Faculty" — create new faculty with department and subject assignments.
7. Visit the Reports page for aggregated analytics — average ratings, feedback counts per category/department, trend data over time, and escalation metrics.

### For Faculty

1. Log in with credentials provided by an admin.
2. Access the faculty dashboard to view all non-5-star feedback from your department, sorted by priority (subject match, pinned items first).
3. Click "Review" on a feedback item to see full details, update status (Pending → In Progress → Resolved), and post comments in the discussion thread.
4. When you mark an item as Resolved, verify the resolution: click Verified/Closed if satisfied, or Verification Failed to send it back for more work.
5. Monitor countdown timers showing remaining time before review/escalation deadlines.

---

## Deployment Notes

- **Production SECRET_KEY**: Must be set via the `SECRET_KEY` environment variable. The application will refuse to start without it when `DEBUG=False`.
- **Database**: For production, use MySQL with a proper `DATABASE_URL` (e.g., `mysql+pymysql://user:password@host/dbname`). SQLite is suitable for development and testing only.
- **Environment variables**: Load `.env` via a process manager or shell export before starting the app. Never commit `.env` to version control.

---

## Screenshots

| Student Registration | Student Dashboard |
|----------------------|-------------------|
| ![Registration](docs/screenshots/registration.png) | ![Dashboard](docs/screenshots/student_dashboard.png) |

| Admin Dashboard | Feedback Detail |
|-----------------|-----------------|
| ![Admin Table](docs/screenshots/admin_dashboard.png) | ![Detail](docs/screenshots/feedback_detail.png) |

| Reports Page | Login Screen |
|-------------|--------------|
| ![Reports](docs/screenshots/reports.png) | ![Login](docs/screenshots/login.png) |

---

## License

This project was developed as an academic exercise for the Object-Oriented Software Engineering lab. It is intended for educational purposes only.

---

## Author

**Aum Namaha** — Final-Year CSE/AIML Student  
Object-Oriented Software Engineering Lab Project