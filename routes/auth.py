import random
import string
from datetime import datetime, timedelta

import bcrypt
from flask import (Blueprint, flash, redirect, render_template,
                   request, session, url_for)
from flask_mail import Message

from extensions import mail, mongo

auth_bp = Blueprint('auth', __name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def gen_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


# ── routes ────────────────────────────────────────────────────────────────────

@auth_bp.route('/')
def index():
    if session.get('user_id'):
        return redirect(url_for('dashboard.home'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = mongo.db.users.find_one({'email': email})
        if user and check_pw(password, user['password']):
            session.permanent = False
            session['user_id']  = str(user['_id'])
            session['email']    = user['email']
            session['fullname'] = user['fullname']
            return redirect(url_for('dashboard.home'))

        flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('user_id'):
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        fullname = request.form.get('fullname', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if not all([email, fullname, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('auth/signup.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/signup.html')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/signup.html')

        if mongo.db.users.find_one({'email': email}):
            flash('Email already registered. Please log in.', 'danger')
            return render_template('auth/signup.html')

        mongo.db.users.insert_one({
            'email':            email,
            'fullname':         fullname,
            'password':         hash_pw(password),
            'created_at':       datetime.utcnow(),
            'skills':           [],
            'resume_score':     None,
            'target_companies': [],
            'learning_path':    [],
            'interview_sessions': [],
            'projects':         [],
            'placement_probability': 0,
        })
        flash('Account created successfully! Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        step = request.form.get('step', '1')

        # ── Step 1 : send OTP ────────────────────────────────────────────────
        if step == '1':
            email = request.form.get('email', '').strip().lower()
            user  = mongo.db.users.find_one({'email': email})

            if not user:
                flash('No account found with that email.', 'danger')
                return render_template('auth/forgot.html', step=1)

            otp    = gen_otp()
            expiry = datetime.utcnow() + timedelta(minutes=10)
            mongo.db.otps.delete_many({'email': email})
            mongo.db.otps.insert_one({'email': email, 'otp': otp, 'expires_at': expiry})

            try:
                msg = Message('PlacementAI – Password Reset OTP', recipients=[email])
                msg.html = f"""
                <div style="font-family:Arial,sans-serif;max-width:480px;
                            margin:auto;background:#f9f9ff;padding:32px;border-radius:12px;">
                  <h2 style="color:#6c63ff;">🎯 PlacementAI</h2>
                  <p>Your one-time password for password reset:</p>
                  <h1 style="letter-spacing:14px;color:#6c63ff;font-size:42px;">{otp}</h1>
                  <p>This OTP expires in <strong>10 minutes</strong>.</p>
                  <p style="color:#999;font-size:12px;">
                    If you did not request this, please ignore this email.
                  </p>
                </div>"""
                mail.send(msg)
                flash(f'OTP sent to {email}', 'success')
            except Exception as exc:
                flash(f'Failed to send OTP: {exc}', 'danger')
                return render_template('auth/forgot.html', step=1)

            return render_template('auth/forgot.html', step=2, email=email)

        # ── Step 2 : verify OTP ──────────────────────────────────────────────
        elif step == '2':
            email     = request.form.get('email', '').strip().lower()
            otp_input = request.form.get('otp', '').strip()
            record    = mongo.db.otps.find_one({'email': email, 'otp': otp_input})

            if not record or record['expires_at'] < datetime.utcnow():
                flash('Invalid or expired OTP.', 'danger')
                return render_template('auth/forgot.html', step=2, email=email)

            return render_template('auth/forgot.html', step=3, email=email, otp=otp_input)

        # ── Step 3 : set new password ────────────────────────────────────────
        elif step == '3':
            email     = request.form.get('email', '').strip().lower()
            otp_input = request.form.get('otp', '').strip()
            new_pass  = request.form.get('new_password', '')
            confirm   = request.form.get('confirm_password', '')

            if new_pass != confirm:
                flash('Passwords do not match.', 'danger')
                return render_template('auth/forgot.html', step=3, email=email, otp=otp_input)

            if len(new_pass) < 8:
                flash('Password must be at least 8 characters.', 'danger')
                return render_template('auth/forgot.html', step=3, email=email, otp=otp_input)

            mongo.db.users.update_one({'email': email}, {'$set': {'password': hash_pw(new_pass)}})
            mongo.db.otps.delete_many({'email': email})
            flash('Password reset successfully! Please sign in.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/forgot.html', step=1)


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
