# Student Feedback Management System

A web-based application for students to submit structured feedback about campus life (food, faculty, infrastructure, events, etc.) and for administrators to view, categorize, track, and resolve that feedback. Built as an Object-Oriented Software Engineering (OOSE) lab project.

---

## Features

- **Student Registration & Login** — Students register using roll number/email and password; secure session-based authentication with hashed passwords.
- **Feedback Submission** — Submit feedback categorized into Food, Faculty, Infrastructure, Events, or Other, with a 1–5 star rating and optional text comment. Toggle anonymous submission.
- **Student Dashboard** — View personal feedback history with current status (Pending / In Progress / Resolved).
- **Admin Dashboard** — View all student feedback in an organized table with multi-criteria filtering (category, rating, status, date range) and keyword search.
- **Feedback Management** — Admins can update feedback status through the workflow: Pending → In Progress → Resolved.
- **Reports & Analytics** — Visual summary of average ratings per category, feedback volume trends over time, and categorical breakdowns.
- **Anonymous Feedback** — Student identity is hidden from all admin-facing queries when anonymous mode is enabled (enforced at the database query layer).
- **Role-Based Access Control** — Strict separation between student and admin privileges.

---

## Tech Stack

| Layer        | Technology                        |
|-------------|-----------------------------------|
| Frontend    | HTML5, CSS3, Vanilla JavaScript   |
| Backend     | Python 3 · Flask (microframework) |
| Database    | MySQL                             |
| ORM         | SQLAlchemy                        |
| Security    | werkzeug.security (password hashing), Flask sessions |

---

## Folder Structure

```
Student_Feedback/
├── app.py                  # Application factory & entry point
├── config.py               # Configuration settings (DB URI, secret key)
├── models.py               # SQLAlchemy ORM models: User, Feedback
├── schema.sql              # Raw MySQL schema for database creation
├── seed.py                 # Seed script to create admin account(s)
├── requirements.txt        # Python dependencies
├── README.md               # This file
│
├── blueprints/             # Modular Flask route blueprints
│   ├── __init__.py
│   ├── auth.py             # Registration, login, logout routes
│   ├── student.py          # Student dashboard & feedback submission
│   └── admin.py            # Admin dashboard, filters, status updates, reports
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Base layout with navigation
│   ├── login.html
│   ├── register.html
│   ├── student_dashboard.html
│   ├── admin_dashboard.html
│   ├── feedback_detail.html
│   └── reports.html
│
├── static/                 # Static assets
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── script.js
│
└── instance/               # SQLite fallback / runtime data (git-ignored)
    └── feedback.db
```

---

## Installation & Setup

### Prerequisites

- Python 3.8 or later
- MySQL Server 5.7+ / 8.0+
- pip (Python package manager)

### Step 1 — Clone the Repository

```bash
git clone https://github.com/Aumnamaha/Student_Feedback_portal.git
cd Student_Feedback
```

### Step 2 — Create the MySQL Database

```sql
CREATE DATABASE student_feedback;
USE student_feedback;
SOURCE schema.sql;   -- or execute schema.sql contents in your MySQL client
```

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure the Application

Edit `config.py` and set:

- `MYSQL_HOST`: Your MySQL host (usually `localhost`)
- `MYSQL_USER`: Your MySQL username
- `MYSQL_PASSWORD`: Your MySQL password
- `MYSQL_DB`: Database name (`student_feedback`)
- `SECRET_KEY`: A random secret key for session management

### Step 5 — Seed an Admin Account

```bash
python seed.py
```

This creates the default admin user. Student accounts are self-registered through `/register`.

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
4. View your submitted feedback and track its resolution status.

### For Administrators

1. Log in with admin credentials (seeded via `seed.py`).
2. Access the admin dashboard to view all student feedback.
3. Use filters (category, rating, status, date range) and keyword search to narrow results.
4. Click on a feedback entry to update its status: Pending → In Progress → Resolved.
5. Visit the Reports page for aggregated analytics — average ratings, feedback counts per category, and trend data over time.

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
