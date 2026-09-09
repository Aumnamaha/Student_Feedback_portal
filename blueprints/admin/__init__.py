"""Admin blueprint — manage all feedback, filters, reports.

Route layout per PROJECT.md:
    /admin/dashboard        – all feedback table with filters
    /admin/feedback/<id>    – view/update single feedback status
    /reports                – summary charts/stats (root-level)
"""

from flask import Blueprint, render_template

admin_bp = Blueprint('admin', __name__, template_folder='../../templates')


@admin_bp.route('/dashboard')
def dashboard():
    """Placeholder admin dashboard (routes to be implemented)."""
    return render_template(
        'admin_dashboard.html',
        _placeholder=True,
    )


# Actual filter/search/status-update routes will follow.
