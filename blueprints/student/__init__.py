"""Student dashboard blueprint — submit feedback and view history."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import Feedback, db
from blueprints.auth.routes import login_required

student_bp = Blueprint('student', __name__, template_folder='../../templates')


@student_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    """Student dashboard — submit new feedback + view own history."""

    # --- POST: submit new feedback ---
    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        rating_str = request.form.get('rating', '').strip()
        comment = request.form.get('comment', '').strip()
        is_anonymous = request.form.get('anonymous') == 'on'

        # --- validation ---
        if not category:
            flash('Please select a feedback category.', 'error')
            return _render_dashboard(request.form)

        try:
            rating = int(rating_str)
            if rating < 1 or rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            flash('Rating must be an integer between 1 and 5.', 'error')
            return _render_dashboard(request.form)

        if not comment:
            flash('Please write a comment.', 'error')
            return _render_dashboard(request.form)

        # --- create feedback record ---
        fb = Feedback(
            student_id=session['user_id'],
            category=category,
            rating=rating,
            comment=comment,
            is_anonymous=is_anonymous,
        )
        db.session.add(fb)
        db.session.commit()

        flash('Feedback submitted successfully!', 'success')
        return redirect(url_for('student.dashboard'))

    # --- GET: render dashboard with history ---
    return _render_dashboard()


def _render_dashboard(submitted_data=None):
    """Render the student dashboard template.

    Parameters
    ----------
    submitted_data : dict or None
        Form data to repopulate on validation failure.
    """
    from models import User

    user = db.session.get(User, session['user_id'])
    if user is None:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    # Fetch own feedback ordered by most recent first
    history = (
        Feedback.query
        .filter_by(student_id=user.id)
        .order_by(Feedback.created_at.desc())
        .all()
    )

    return render_template(
        'student_dashboard.html',
        user=user,
        feedback_history=history,
        submitted=submitted_data or {},
    )
