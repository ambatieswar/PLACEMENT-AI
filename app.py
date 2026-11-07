import os
import logging
import hmac
import secrets
from flask import Flask, abort, jsonify, request, session
from dotenv import load_dotenv
from extensions import mongo, mail, sess

load_dotenv()

def create_app(config_override=None):
    app = Flask(__name__)
    is_vercel = bool(os.getenv('VERCEL'))

    # ── Core config ──────────────────────────────────────────────────────────
    configured_secret = (
        (config_override or {}).get('SECRET_KEY')
        or os.getenv('SECRET_KEY', '')
    ).strip()
    app.config['SECRET_KEY']          = configured_secret or 'development-only-secret'
    app.config['MONGO_URI']           = os.getenv('MONGO_URI', '')
    app.config['MISTRAL_API_KEY']     = os.getenv('MISTRAL_API_KEY', '')
    app.config['GEMINI_API_KEY']      = os.getenv('GEMINI_API_KEY', '')
    app.config['FALLBACK_STORAGE_MODE'] = os.getenv(
        'FALLBACK_STORAGE_MODE',
        'memory' if is_vercel else 'file',
    )
    app.config['FALLBACK_STORAGE_PATH'] = os.getenv(
        'FALLBACK_STORAGE_PATH', os.path.join(app.root_path, 'data', 'placementai_fallback.json')
    )

    # ── Mail (Gmail SMTP + App-Password) ─────────────────────────────────────
    app.config['MAIL_SERVER']         = 'smtp.gmail.com'
    app.config['MAIL_PORT']           = 587
    app.config['MAIL_USE_TLS']        = True
    app.config['MAIL_USERNAME']       = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD']       = os.getenv('MAIL_APP_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')

    # ── Server-side session ───────────────────────────────────────────────────
    app.config['USE_SERVER_SIDE_SESSION'] = not is_vercel
    app.config['SESSION_TYPE']        = 'filesystem'
    app.config['SESSION_PERMANENT']   = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('COOKIE_SECURE', '').lower() == 'true'
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
    if config_override:
        app.config.update(config_override)
    configured_secret = app.config['SECRET_KEY'].strip()

    @app.context_processor
    def inject_security_helpers():
        def csrf_token():
            token = session.get('_csrf_token')
            if not token:
                token = secrets.token_urlsafe(32)
                session['_csrf_token'] = token
            return token
        return {'csrf_token': csrf_token}

    @app.before_request
    def protect_state_changes():
        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return None
        expected = session.get('_csrf_token')
        supplied = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            if request.path.startswith('/api/'):
                return jsonify(success=False, error='CSRF validation failed'), 400
            abort(400, description='CSRF validation failed')
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self' https://cdnjs.cloudflare.com https://fonts.googleapis.com "
            "https://fonts.gstatic.com; img-src 'self' data:; style-src 'self' "
            "'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",
        )
        return response

    # ── Init extensions ───────────────────────────────────────────────────────
    mongo.init_app(app)
    mail.init_app(app)
    if app.config['USE_SERVER_SIDE_SESSION']:
        sess.init_app(app)
    app.config['DEPENDENCY_STATUS'] = {
        'configuration': {
            'valid': bool(configured_secret) and configured_secret != 'development-only-secret',
            'warnings': [] if configured_secret and configured_secret != 'development-only-secret' else
            ['SECRET_KEY is not configured; using a development-only secret'],
        },
        'mongodb': {
            'available': not mongo.using_fallback,
            'fallback': mongo.using_fallback,
            'message': mongo.reason or 'MongoDB connected',
        },
        'mistral': {
            'available': bool(app.config['MISTRAL_API_KEY']),
            'message': 'Configured' if app.config['MISTRAL_API_KEY']
            else 'MISTRAL_API_KEY is not configured',
        },
        'gemini': {
            'available': bool(app.config['GEMINI_API_KEY']),
            'message': 'Configured' if app.config['GEMINI_API_KEY']
            else 'GEMINI_API_KEY is not configured',
        },
    }
    if mongo.using_fallback:
        logging.getLogger(__name__).warning("Using local storage fallback: %s", mongo.reason)

    # ── Register blueprints ───────────────────────────────────────────────────
    from routes.auth      import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.features  import features_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(features_bp)

    @app.errorhandler(413)
    def request_too_large(_error):
        if request.path.startswith('/api/'):
            return jsonify(success=False, error='Request exceeds the 10 MB limit'), 413
        return 'Request exceeds the 10 MB limit', 413

    @app.get('/api/status')
    def status():
        return {
            'success': True,
            'dependencies': app.config['DEPENDENCY_STATUS'],
        }

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '').lower() == 'true')
