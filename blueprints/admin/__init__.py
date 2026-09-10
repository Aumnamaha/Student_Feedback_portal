"""Admin blueprint — manage all feedback, filters, reports.

Route layout per PROJECT.md:
    /admin/dashboard        – all feedback table with filters
    /admin/feedback/<id>    – view/update single feedback status
    /reports                – summary charts/stats (root-level)
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import Feedback, User, db
from blueprints.auth.routes import login_required, admin_required

admin_bp = Blueprint('admin', __name__, template_folder='../../templates')


# ------------------------------------------------------------------ #
#  ADMIN DASHBOARD — all feedback with filters                         #
# ------------------------------------------------------------------ #

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard: table view of all feedback with filter bar."""

    # --- build query from filters ---
    category = request.args.get('category', '').strip() or None
    rating_str = request.args.get('rating', '').strip() or None
    status = request.args.get('status', '').strip() or None
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    keyword = request.args.get('keyword', '').strip() or None

    query = Feedback.admin_query(
        db.session,
        category=category,
        rating=int(rating_str) if rating_str else None,
        status=status,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
    )

    feedback_list = [fb.to_admin_dict() for fb in query.all()]
    total_count = len(feedback_list)

    # Build filter state dict for template repopulation
    filters = {
        'category': category or '',
        'rating': rating_str or '',
        'status': status or '',
        'date_from': date_from or '',
        'date_to': date_to or '',
        'keyword': keyword or '',
    }

    # Pre-compute whether any filters are active (Jinja doesn't have built-in `any()`)
    has_active_filters = any(v for v in filters.values())

    return render_template(
        'admin_dashboard.html',
        feedback_list=feedback_list,
        total_count=total_count,
        filters=filters,
        has_active_filters=has_active_filters,
    )


# ------------------------------------------------------------------ #
#  FEEDBACK DETAIL — view + update status                              #
# ------------------------------------------------------------------ #

@admin_bp.route('/feedback/<int:fb_id>')
@login_required
@admin_required
def feedback_detail(fb_id):
    """View full feedback detail and update its status."""
    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    # Admin-facing dict (PII hidden for anonymous rows at query/serial level)
    feedback_data = fb.to_admin_dict()

    return render_template(
        'admin_feedback_detail.html',
        feedback=feedback_data,
        is_anonymous=bool(fb.is_anonymous),
    )


@admin_bp.route('/feedback/<int:fb_id>/status', methods=['POST'])
@login_required
@admin_required
def update_status(fb_id):
    """Update the status of a single feedback entry."""
    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    new_status = request.form.get('status', '').strip()
    valid_statuses = {'Pending', 'In Progress', 'Resolved'}

    if new_status not in valid_statuses:
        flash(f'Invalid status. Must be one of: {", ".join(valid_statuses)}', 'error')
        return redirect(url_for('admin.feedback_detail', fb_id=fb.id))

    old_status = fb.status
    fb.status = new_status
    db.session.commit()

    flash(
        f'Status updated from "{old_status}" to "{new_status}".',
        'success'
    )
    return redirect(url_for('admin.feedback_detail', fb_id=fb.id))


# ------------------------------------------------------------------ #
#  PLACEHOLDER: REPORTS                                                #
# ------------------------------------------------------------------ #

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    """Summary reports — to be implemented."""
    return render_template(
        'reports.html',
        _placeholder=True,
    )
