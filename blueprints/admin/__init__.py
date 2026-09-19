"""Admin blueprint — manage all feedback, filters, reports.

Route layout per PROJECT.md:
    /admin/dashboard        – all feedback table with filters + Faculty Review section
    /admin/feedback/<id>    – view/update single feedback status
    /reports                – summary charts/stats (root-level)
"""

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from models import Feedback, User, _is_overdue, db
from blueprints.auth.routes import login_required, admin_required

admin_bp = Blueprint('admin', __name__, template_folder='../../templates')


# ------------------------------------------------------------------ #
#  HELPER — determine if a feedback item is "escalated"               #
# ------------------------------------------------------------------ #

def _is_escalated(fb):
    """Return True if the feedback item should show an Escalation badge.

    Criteria (any one triggers escalation):
      - ``failed_verification_count >= 3``
      - Status is **Pinned** and ``escalation_deadline`` has passed
      - Status is **Resolved** but ``escalation_deadline`` exists and passed
        (faculty didn't verify in time)
    """
    if fb.failed_verification_count and int(fb.failed_verification_count) >= 3:
        return True
    # Pinned items are escalated when their escalation deadline has passed
    if fb.status == "Pinned" and _is_overdue(fb.escalation_deadline):
        return True
    # Resolved items that have an escalation deadline past (faculty didn't verify)
    if fb.status == "Resolved" and fb.escalation_deadline and _is_overdue(fb.escalation_deadline):
        return True
    return False


# ------------------------------------------------------------------ #
#  ADMIN DASHBOARD — all feedback with filters + Faculty Review       #
# ------------------------------------------------------------------ #

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard: table view of all feedback with filter bar,
    plus a dedicated 'Faculty Review' section for Resolved/Pinned items."""

    # --- build query from filters (main table) ---
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

    has_active_filters = any(v for v in filters.values())

    # ------------------------------------------------------------------
    #  Faculty Review section — Resolved (pending verification) + Pinned
    #  Also respects active filters so the main table + review section
    #  stay consistent. Only shown when no conflicting status filter.
    # ------------------------------------------------------------------
    show_review_section = True
    if status and status not in ('Resolved', 'Pinned'):
        # User filtered by a non-review status — hide the review section
        show_review_section = False

    faculty_review = []
    resolved_count = 0
    pinned_count = 0
    escalation_count = 0

    if show_review_section:
        review_query = db.session.query(Feedback).filter(
            Feedback.status.in_(['Resolved', 'Pinned'])
        )

        # Apply same filters as main query (category, keyword)
        if category:
            review_query = review_query.filter(Feedback.category == category)
        if keyword:
            review_query = review_query.filter(Feedback.comment.ilike(f"%{keyword}%"))

        review_query = review_query.order_by(Feedback.created_at.desc())

        for fb in review_query.all():
            d = fb.to_admin_dict()
            d['_is_escalated'] = _is_escalated(fb)
            d['_failed_count'] = int(fb.failed_verification_count or 0)
            faculty_review.append(d)

    resolved_count = sum(1 for f in faculty_review if f['status'] == 'Resolved')
    pinned_count = sum(1 for f in faculty_review if f['status'] == 'Pinned')
    escalation_count = sum(1 for f in faculty_review if f['_is_escalated'])

    return render_template(
        'admin_dashboard.html',
        feedback_list=feedback_list,
        total_count=total_count,
        filters=filters,
        has_active_filters=has_active_filters,
        # Faculty Review section data
        faculty_review=faculty_review,
        resolved_count=resolved_count,
        pinned_count=pinned_count,
        escalation_count=escalation_count,
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
    escalation_badge = _is_escalated(fb)

    return render_template(
        'admin_feedback_detail.html',
        feedback=feedback_data,
        is_anonymous=bool(fb.is_anonymous),
        escalation_badge=escalation_badge,
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
#  ADMIN VERIFICATION ROUTES                                          #
# ------------------------------------------------------------------ #

@admin_bp.route('/feedback/<int:fb_id>/verify-success', methods=['POST'])
@login_required
@admin_required
def verify_success(fb_id):
    """Admin marks a Resolved item as Verified/Closed."""
    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        fb.verify_success()
        db.session.commit()
        flash(f'Feedback #{fb.id} marked as Verified/Closed.', 'success')
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('admin.feedback_detail', fb_id=fb.id))


@admin_bp.route('/feedback/<int:fb_id>/verify-failure', methods=['POST'])
@login_required
@admin_required
def verify_failure(fb_id):
    """Admin marks a Resolved item as Verification Failed → reverts to In Progress."""
    fb = db.session.get(Feedback, fb_id)
    if fb is None:
        flash('Feedback not found.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        fb.verify_failure()
        db.session.commit()
        flash(
            f'Verification failed for #{fb.id}. Count incremented to '
            f'{fb.failed_verification_count}. Status reverted to In Progress.',
            'warning',
        )
    except ValueError as e:
        flash(str(e), 'error')

    return redirect(url_for('admin.feedback_detail', fb_id=fb.id))


# ------------------------------------------------------------------ #
#  REPORTS — aggregate stats (no joins → no PII exposure possible)     #
# ------------------------------------------------------------------ #

@admin_bp.route('/reports')
@login_required
@admin_required
def reports():
    """Summary reports: avg rating per category, count by status,
    and trend over time (weekly/monthly).  Uses only the ``feedback``
    table — no joins to ``users``, so student PII is impossible to leak.

    New metrics (verification workflow):
      - Feedback count **by department**
      - Average resolution time for faculty-routed feedback
      - Total escalation count (Pinned + failed_verification_count >= 3)
    """

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
                (Feedback.status == "Pinned", 4),
                (Feedback.status == "Verified/Closed", 5),
                (Feedback.status == "Verification Failed", 6),
            )
        )
        .all()
    )

    # Trend over time — grouped by month and week
    # Monthly: substr(created_at, 1, 7) → "YYYY-MM" works on BOTH SQLite & MySQL
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

    # Weekly trend — dialect-aware so it works on both SQLite (tests) and MySQL (prod)
    from datetime import date as _date, timedelta as _timedelta

    today = _date.today()
    weeks_back = 12
    week_start = today - _timedelta(weeks=weeks_back)

    dialect_name = db.session.get_bind().dialect.name if hasattr(db.session, 'get_bind') else 'sqlite'

    if dialect_name == 'mysql':
        # MySQL: CONCAT(YEAR(), '-W', LPAD(WEEK())) → "2026-W37" format
        weekly_trend = (
            db.session.query(
                func.concat(func.year(Feedback.created_at), "-W", func.lpad(func.week(Feedback.created_at, 1), 2, "0")).label("week"),
                func.count(Feedback.id).label("count"),
                func.round(func.avg(Feedback.rating), 2).label("avg_rating"),
            )
            .group_by(func.year(Feedback.created_at), func.week(Feedback.created_at, 1))
            .order_by(func.year(Feedback.created_at), func.week(Feedback.created_at, 1))
            .all()
        )
    else:
        # SQLite fallback: use month-level grouping since strftime has no ISO week
        weekly_trend = monthly_trend

    # Compute max values for CSS bar widths
    max_monthly = max((row[1] for row in monthly_trend), default=1) or 1
    max_weekly = max((row[1] for row in weekly_trend), default=1) or 1
    max_status = max((row[1] for row in status_counts), default=1) or 1

    # ===== NEW: Feedback count by department =====
    dept_stats = (
        db.session.query(
            Feedback.department,
            func.count(Feedback.id).label("count"),
        )
        .filter(Feedback.department.isnot(None))
        .group_by(Feedback.department)
        .order_by(func.count(Feedback.id).desc())
        .all()
    )

    # ===== NEW: Average resolution time for faculty-routed feedback =====
    # Resolution time = updated_at (when status becomes Resolved or Verified/Closed) - created_at
    # Calculated in Python to be dialect-agnostic (works on both MySQL and SQLite)
    all_matching = (
        db.session.query(Feedback)
        .filter(
            Feedback.status.in_(['Resolved', 'Verified/Closed']),
            Feedback.resolved_by_faculty_id.isnot(None),
        )
        .all()
    )

    avg_resolution_secs = None
    if all_matching:
        total_secs = 0.0
        count = 0
        for fb in all_matching:
            if fb.created_at and fb.updated_at:
                ca = fb.created_at.replace(tzinfo=None) if fb.created_at.tzinfo else fb.created_at
                ua = fb.updated_at.replace(tzinfo=None) if fb.updated_at.tzinfo else fb.updated_at
                diff = (ua - ca).total_seconds()
                total_secs += max(0, diff)
                count += 1
        avg_resolution_secs = total_secs / count if count > 0 else None

    def _format_duration(seconds):
        """Convert seconds to a human-readable string."""
        if seconds is None:
            return "N/A"
        hours, remainder = divmod(int(seconds), 3600)
        minutes, _ = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    # ===== NEW: Escalation count =====
    # Items that are Pinned (escalated) + items with failed_verification_count >= 3
    pinned_items = Feedback.query.filter(
        Feedback.status == "Pinned",
    ).count()

    high_fail_items = Feedback.query.filter(
        Feedback.failed_verification_count >= 3,
    ).count()

    total_escalations = pinned_items + high_fail_items

    return render_template(
        'reports.html',
        category_stats=cat_stats,
        status_counts=status_counts,
        monthly_trend=monthly_trend,
        weekly_trend=weekly_trend,
        max_monthly=max_monthly,
        max_weekly=max_weekly,
        max_status=max_status,
        # New verification-report metrics
        dept_stats=dept_stats,
        avg_resolution_time=_format_duration(avg_resolution_secs),
        pinned_count=pinned_items,
        high_fail_count=high_fail_items,
        total_escalations=total_escalations,
    )
