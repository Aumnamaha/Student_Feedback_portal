"""Faculty dashboard blueprint — view and act on department feedback."""

from flask import Blueprint

faculty_bp = Blueprint('faculty', __name__, template_folder='../../templates')


# Import routes after blueprint is defined (avoids circular imports)
from . import routes  # noqa: F401
