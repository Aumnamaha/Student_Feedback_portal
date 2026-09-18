"""Faculty routes — dashboard, feedback detail, status transitions, comments."""

from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from models import Comment, Feedback, Faculty, _is_overdue, db
from blueprints.auth.routes import login_required, faculty_required

# Import the blueprint from the parent module (avoids circular imports)
from . import faculty_bp


# ------------------------------------------------------------------ #
#  BEFORE REQUEST — initialize g.faculty for every protected route     #
# ------------------------------------------------------------------ #

@faculty_bp.before_request
def _load_faculty():
    """Load the current faculty into ``g.faculty`` so routes don't need
    to re-query the database on every call."""
    if 'faculty_id' in session:
        g.faculty = db.session.get(Faculty, session['faculty_id'])
    else:
        g.faculty = None


# ------------------------------------------------------------------ #
#  HELPER — escalate overdue feedback                                  #
# ------------------------------------------------------------------ #

def _check_and_escalate():
    """Mark overdue feedback as Pinned / set escalation_deadline.

    Called on every dashboard load (acts like a lightweight background job).
    Finds all unresolved feedback in the logged-in faculty's department where
    review_deadline has passed with no faculty action, then:
      - Sets ``status = 'Pinned'``  (visual flag for "nobody reviewed it")
      - Sets ``escalation_deadline = now + 3 days``

    Returns the number of items escalated.
    """
    if g.faculty is None:
        return 0

    department = g.faculty.department
    now = datetime.now(timezone.utc)

    # Find feedback where review_deadline has passed, no escalation set yet,
    # and not already closed/failed verification.
    # We filter in Python to handle naive vs aware timezone mismatches.
    candidates = (
        Feedback.query
        .filter(
            Feedback.department == department,
            Feedback.review_deadline != None,
            Feedback.escalation_deadline == None,
            Feedback.status.notin_(
                ('Verified/Closed', 'Verification Failed')
            ),
        )
        .all()
    )

    count = 0
    for fb in candidates:
        if _is_overdue(fb.review_deadline):
            fb.status = "Pinned"
            # Store as naive UTC to match SQLite default behavior
            fb.escalation_deadline = datetime.now(timezone.utc).replace(
                tzinfo=None,
            ) + timedelta(days=3)
            count += 1

    if count > 0:
        db.session.commit()

    return count


# ------------------------------------------------------------------ #
#  FACULTY DASHBOARD                                                   #
# ------------------------------------------------------------------ #

@faculty_bp.route('/dashboard')
@login_required
@faculty_required
def dashboard():
    """Faculty dashboard — show department feedback with countdowns."""

    if g.faculty is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    faculty = g.faculty

    # --- run escalation check (background-like on each load) ---
    _check_and_escalate()

    # Query feedback for this department, exclude 5-star ratings
    query = Feedback.faculty_query(
        db.session,
        department=faculty.department,
        subject=faculty.subject_taught,
    )

    feedback_list = [
        fb.to_faculty_dict(faculty_subject=faculty.subject_taught)
        for fb in query.all()
    ]

    # Count by status for summary stats
    all_dept_feedback = (
        Feedback.query
        .filter(Feedback.department == faculty.department, Feedback.rating != 5)
        .all()
    )
    pending_count = sum(1 for f in all_dept_feedback if f.status == 'Pending')
    escalated_count = sum(
        1 for f in all_dept_feedback
        if _is_overdue(f.escalation_deadline)
    )

    return render_template(
        'faculty_dashboard.html',
        faculty=faculty,
        feedback_list=feedback_list,
        pending_count=pending_count,
        escalated_count=escalated_count,
    )


# ------------------------------------------------------------------ #
#  FEEDBACK DETAIL — view + comment + status transition                #
# ------------------------------------------------------------------ #

@faculty_bp.route('/feedback/<int:fb_id>')
@login_required
@faculty_required
def feedback_detail(fb_id):
    """View a single feedback item, post comments, update status."""

    if g.faculty is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    faculty = g.faculty

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('faculty.dashboard'))

    # Only show feedback from the faculty's department (with 5-star filter)
    if fb.department != faculty.department or fb.rating == 5:
        flash('You do not have access to this feedback item.', 'error')
        return redirect(url_for('faculty.dashboard'))

    # Serialize for display
    feedback_data = fb.to_faculty_dict(faculty_subject=faculty.subject_taught)

    # Load comments — only faculty can post, students view read-only
    comments = (
        Comment.query
        .filter_by(feedback_id=fb.id, author_type='faculty')
        .order_by(Comment.created_at.asc())
        .all()
    )
    comment_data = [
        {
            "id": c.id,
            "text": c.text,
            "created_at": c.created_at,
        }
        for c in comments
    ]

    return render_template(
        'faculty_feedback_detail.html',
        feedback=feedback_data,
        comments=comment_data,
        can_comment=True,  # matching faculty can always comment
    )


@faculty_bp.route('/feedback/<int:fb_id>/status', methods=['POST'])
@login_required
@faculty_required
def update_status(fb_id):
    """Transition feedback status: Pending → In Progress → Resolved."""

    if g.faculty is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    faculty = g.faculty

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('faculty.dashboard'))

    new_status = request.form.get('status', '').strip()
    valid_statuses = {'Pending', 'In Progress', 'Resolved'}

    if new_status not in valid_statuses:
        flash(f'Invalid status. Must be one of: {", ".join(valid_statuses)}', 'error')
        return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))

    old_status = fb.status
    fb.status = new_status
    fb.resolved_by_faculty_id = faculty.id
    db.session.commit()

    flash(
        f'Status updated from "{old_status}" to "{new_status}".',
        'success'
    )
    return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))


@faculty_bp.route('/feedback/<int:fb_id>/verify', methods=['POST'])
@login_required
@faculty_required
def verify_feedback(fb_id):
    """Verify resolved feedback → Verified/Closed or Verification Failed."""

    if g.faculty is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    faculty = g.faculty

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('faculty.dashboard'))

    action = request.form.get('action', '').strip()  # 'success' or 'failure'

    try:
        if action == 'success':
            fb.verify_success()
            flash('Feedback marked as Verified/Closed.', 'success')
        elif action == 'failure':
            fb.verify_failure()
            flash(
                f'Verification failed. Count incremented to '
                f'{fb.failed_verification_count}.',
                'warning',
            )
        else:
            flash('Invalid action.', 'error')
            return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))

        db.session.commit()
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))


# ------------------------------------------------------------------ #
#  COMMENT THREAD API                                                  #
# ------------------------------------------------------------------ #

@faculty_bp.route('/feedback/<int:fb_id>/comment', methods=['POST'])
@login_required
def add_comment(fb_id):
    """Post a comment on feedback (only matching faculty)."""

    if session.get('role') != 'faculty':
        return jsonify({"error": "Access denied"}), 403

    if g.faculty is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    faculty = g.faculty

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        return jsonify({"error": "Not found"}), 404

    # Only matching department faculty can comment
    if fb.department != faculty.department:
        return jsonify({"error": "Access denied"}), 403

    text = request.form.get('text', '').strip() or (
        request.json.get('text', '').strip() if request.is_json else ''
    )

    if not text:
        if request.is_json:
            return jsonify({"error": "Comment cannot be empty"}), 400
        flash('Please write a comment.', 'error')
        return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))

    comment = Comment(
        feedback_id=fb.id,
        author_type='faculty',
        author_id=faculty.id,
        text=text,
    )
    db.session.add(comment)
    db.session.commit()

    if request.is_json:
        return jsonify({
            "id": comment.id,
            "text": comment.text,
            "created_at": comment.created_at.isoformat(),
        }), 201

    flash('Comment posted.', 'success')
    return redirect(url_for('faculty.feedback_detail', fb_id=fb.id))


@faculty_bp.route('/feedback/<int:fb_id>/comments', methods=['GET'])
@login_required
def get_comments(fb_id):
    """API endpoint to fetch comments for a feedback item.

    Only matching faculty or the submitting student can view.
    """

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        return jsonify({"error": "Not found"}), 404

    role = session.get('role')

    if role == 'faculty':
        from models import Faculty as _Faculty
        faculty = db.session.get(_Faculty, session.get('faculty_id'))
        if faculty is None or fb.department != faculty.department:
            return jsonify({"error": "Access denied"}), 403
    elif role == 'student':
        from models import User as _User
        student = db.session.get(_User, session.get('user_id'))
        if student is None or student.id != fb.student_id:
            return jsonify({"error": "Access denied"}), 403
    else:
        return jsonify({"error": "Unauthorized"}), 401

    comments = (
        Comment.query
        .filter_by(feedback_id=fb.id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    return jsonify([
        {
            "id": c.id,
            "text": c.text,
            "author_type": c.author_type,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ])


# ------------------------------------------------------------------ #
#  COUNTDOWN API — remaining time to deadline                          #
# ------------------------------------------------------------------ #

@faculty_bp.route('/api/countdown/<int:fb_id>', methods=['GET'])
@login_required
def countdown_api(fb_id):
    """Return the remaining seconds until review_deadline (or escalation)."""

    role = session.get('role')

    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        return jsonify({"error": "Not found"}), 404

    # Permission check based on role
    if role == 'faculty':
        from models import Faculty as _Faculty
        faculty = db.session.get(_Faculty, session.get('faculty_id'))
        if faculty is None or fb.department != faculty.department:
            return jsonify({"error": "Not found"}), 404
    elif role == 'student':
        from models import User as _User
        student = db.session.get(_User, session.get('user_id'))
        if student is None or student.id != fb.student_id:
            return jsonify({"error": "Not found"}), 404
    else:
        return jsonify({"error": "Unauthorized"}), 401

    # Normalize deadline to aware for subtraction
    deadline = fb.escalation_deadline or fb.review_deadline
    if deadline is None:
        return jsonify({"seconds_remaining": -1, "status": "no-deadline"})

    now_utc = datetime.now(timezone.utc)
    # If deadline is naive, assume UTC
    if deadline.tzinfo is None:
        diff = (deadline.replace(tzinfo=timezone.utc) - now_utc).total_seconds()
    else:
        diff = (deadline - now_utc).total_seconds()

    status = "overdue" if diff <= 0 else ("escalated" if fb.escalation_deadline and diff < 259200 else "active")

    return jsonify({
        "seconds_remaining": max(0, int(diff)),
        "status": status,
        "deadline_type": "escalation" if fb.escalation_deadline else "review",
    })
