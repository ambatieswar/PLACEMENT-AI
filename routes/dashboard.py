from functools import wraps

from bson import ObjectId
from flask import (Blueprint, flash, redirect, render_template, session, url_for)

from extensions import mongo

dashboard_bp = Blueprint('dashboard', __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@dashboard_bp.route('/dashboard')
@login_required
def home():
    user = mongo.db.users.find_one({'_id': ObjectId(session['user_id'])})
    if user is None:
        session.clear()
        flash(
            'Your session expired because persistent storage is not configured. '
            'Please sign in again after MongoDB is connected.',
            'warning',
        )
        return redirect(url_for('auth.login'))

    stats = {
        'resume_score':          user.get('resume_score', 0) or 0,
        'skills_count':          len(user.get('skills', [])),
        'interview_sessions':    len(user.get('interview_sessions', [])),
        'placement_probability': user.get('placement_probability', 0) or 0,
    }

    recent_activity = list(
        mongo.db.activity.find(
            {'user_id': session['user_id']},
            sort=[('created_at', -1)],
            limit=5,
        )
    )

    return render_template('dashboard/home.html', user=user, stats=stats,
                           activity=recent_activity)
