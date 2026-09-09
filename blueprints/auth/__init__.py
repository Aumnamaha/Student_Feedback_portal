"""Authentication blueprint — handles registration, login, logout."""

from flask import Blueprint

auth_bp = Blueprint('auth', __name__, template_folder='../../templates')


# Import routes after blueprint is defined (avoids circular imports)
from . import routes  # noqa: F401
