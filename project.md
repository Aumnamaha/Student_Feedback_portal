# PROJECT.md — Student Feedback Management System

## Overview
A web-based system for students to submit structured feedback about campus 
life (food, faculty, infrastructure, events, etc.), and for admins to view, 
categorize, track, and resolve that feedback. OOSE lab project.

## Repo
https://github.com/Aumnamaha/Student_Feedback_portal

## Tech Stack
- Frontend: HTML, CSS, JavaScript (vanilla)
- Backend: Python (Flask)
- Database: MySQL
- Auth: Flask sessions, password hashing via werkzeug.security
- DB access: SQLAlchemy

## User Roles
- **Student**: submits and views own feedback
- **Admin**: views all feedback, filters, updates status, sees reports

## Functional Requirements
- Student registration & login (roll number/email + password)
- Admin login (separate role, seeded manually — not self-registerable)
- Submit feedback: category (Food/Faculty/Infrastructure/Events/Other), 
  rating (1-5), text comment, anonymous toggle
- Student: view own feedback history + status
- Admin dashboard: view all feedback in a table; filter by category, 
  rating, status, date range; keyword search in comments
- Admin: update feedback status (Pending → In Progress → Resolved)
- Reports view: average rating per category, feedback count per category, 
  trend over time (weekly/monthly)
- Logout for both roles

## Non-Functional Requirements
- Usability: clean, simple, mobile-responsive UI
- Performance: dashboard loads in 2-3s for hundreds of records
- Security: hashed passwords, role-based access control, anonymous feedback 
  must NEVER expose student identity to admin queries (enforce at query 
  level, not just UI hiding)
- Reliability: no data loss on submission, proper DB transaction handling
- Scalability: schema supports growth without redesign
- Maintainability: modular Flask app (blueprints, separated models/routes/templates)
- Availability: runs reliably on local server for demo

## Database Schema (MySQL)

**users**
| Column | Type | Notes |
|---|---|---|
| id | INT PK AUTO_INCREMENT | |
| name | VARCHAR(100) | |
| email | VARCHAR(100) UNIQUE | |
| roll_number | VARCHAR(50) UNIQUE NULL | for students |
| password_hash | VARCHAR(255) | |
| role | ENUM('student','admin') | |
| created_at | TIMESTAMP | default now |

**feedback**
| Column | Type | Notes |
|---|---|---|
| id | INT PK AUTO_INCREMENT | |
| student_id | INT FK -> users.id | kept for tracking even if anonymous |
| category | ENUM('Food','Faculty','Infrastructure','Events','Other') | |
| rating | TINYINT | 1-5 |
| comment | TEXT | |
| is_anonymous | BOOLEAN | default false |
| status | ENUM('Pending','In Progress','Resolved') | default 'Pending' |
| created_at | TIMESTAMP | default now |
| updated_at | TIMESTAMP | on update |

## Architecture
3-tier:
- Presentation: HTML/CSS/JS templates (Jinja2)
- Application: Flask routes/blueprints (auth, feedback, admin)
- Data: MySQL via SQLAlchemy

## Routes
- `/register`, `/login`, `/logout`
- `/dashboard` (student) — submit feedback + view own history
- `/admin/dashboard` — all feedback table with filters
- `/admin/feedback/<id>` — view/update single feedback status
- `/reports` (admin) — summary charts/stats

## Anonymous Feedback — Critical Security Note
`is_anonymous=True` must hide student identity from ALL admin-facing 
queries/views/exports — enforce at the query layer, not just the UI.

## Deliverables
- `app.py` (app factory pattern)
- `models.py` (SQLAlchemy: User, Feedback)
- `templates/`: login, register, student_dashboard, admin_dashboard, 
  admin_feedback_detail, reports
- `static/`: CSS, JS
- `schema.sql` — creates DB + tables per schema above
- Seed script — at least one admin account
- Flask blueprints: `auth`, `student`, `admin` separated

## Diagrams — Important
Aum builds final UML diagrams himself in StarUML. The local model should 
only generate simple flow/reference sketches (plain text/Mermaid), never 
polished UML, for: Use Case flow, Class relationships, Sequence for 
"Submit Feedback", Activity flow (feedback status lifecycle), ER relationship.

## Report Structure (30 sections — build via sub-prompts, section by section)
1. Title Page · 2. Certificate · 3. Declaration · 4. Acknowledgement · 
5. Abstract · 6. Table of Contents · 7. Introduction · 8. Problem Statement · 
9. Objectives · 10. Existing System · 11. Proposed System · 12. Scope · 
13. Functional Requirements · 14. Non-Functional Requirements · 
15. System Architecture · 16. Use Case Diagram · 17. Class Diagram · 
18. Sequence Diagrams · 19. Activity Diagrams · 20. ER Diagram · 
21. Database Design · 22. UI Design · 23. Implementation · 24. Testing · 
25. Results · 26. Advantages · 27. Limitations · 28. Future Enhancements · 
29. Conclusion · 30. References

Sections 1-6 are administrative/formatting — Aum handles these himself.
Sections 7 onward are what sub-prompts will drive, one or a few sections 
at a time, so the model isn't asked to hold the whole report in context 
at once. Sub-prompt sequence to be provided separately by Aum.

## Current Phase
PROJECT.md complete. Awaiting sub-prompt sequence (starting at section 7) 
before development model selection and build begin.

## Deployment
Local server demo is sufficient. Explain steps mentor-style — never execute 
autonomously.