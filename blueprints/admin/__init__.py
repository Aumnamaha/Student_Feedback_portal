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
#  REPORTS — aggregate stats (no joins → no PII exposure possible)     #
# ------------------------------------------------------------------ #

from sqlalchemy import func

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    """Summary reports: avg rating per category, count by status,
    and trend over time (weekly/monthly).  Uses only the ``feedback``
    table — no joins to ``users``, so student PII is impossible to leak."""

    # --- aggregate helpers (pure SQL aggregates on feedback table) ---

    # Average rating per category + total count
    cat_stats = (
        db.session.query(
            Feedback.category,
            func.round(func.avg(Feedback.rating), 2).label("avg_rating"),
            func.count(Feedback.id).label("count"),
        )
        .group_by(Feedback.category)
        .order_by(func.count(Feedback.id).desc())
        .all()
    )

    # Feedback count by status
    status_counts = (
        db.session.query(
            Feedback.status,
            func.count(Feedback.id).label("count"),
        )
        .group_by(Feedback.status)
        .order_by(
            db.case(
                (Feedback.status == "Pending", 1),
                (Feedback.status == "In Progress", 2),
                (Feedback.status == "Resolved", 3),
            )
        )
        .all()
    )

    # Trend over time — weekly buckets for the last N weeks
    from datetime import date, timedelta

    today = date.today()
    weeks_back = 12
    week_start = today - timedelta(weeks=weeks_back)

    # Use strftime on created_at to group by ISO week
    # SQLite-compatible: use substr(created_at, 1, 7) for YYYY-MM month grouping
    monthly_trend = (
        db.session.query(
            func.substr(Feedback.created_at, 1, 7).label("month"),
            func.count(Feedback.id).label("count"),
            func.round(func.avg(Feedback.rating), 2).label("avg_rating"),
        )
        .group_by(func.substr(Feedback.created_at, 1, 7))
        .order_by(func.substr(Feedback.created_at, 1, 7))
        .all()
    )

    # Weekly trend (ISO week number + year)
    weekly_trend = (
        db.session.query(
            func.strftime("%Y-W%w", Feedback.created_at).label("week"),
            func.count(Feedback.id).label("count"),
            func.round(func.avg(Feedback.rating), 2).label("avg_rating"),
        )
        .group_by(func.strftime("%Y-W%w", Feedback.created_at))
        .order_by(func.strftime("%Y-W%w", Feedback.created_at))
        .all()
    )

    # Compute max values for CSS bar widths
    max_monthly = max((row[1] for row in monthly_trend), default=1) or 1
    max_weekly = max((row[1] for row in weekly_trend), default=1) or 1
    max_status = max((row[1] for row in status_counts), default=1) or 1

    return render_template(
        'reports.html',
        category_stats=cat_stats,
        status_counts=status_counts,
        monthly_trend=monthly_trend,
        weekly_trend=weekly_trend,
        max_monthly=max_monthly,
        max_weekly=max_weekly,
        max_status=max_status,
    )
