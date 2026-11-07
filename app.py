import os
import logging
from flask import Flask
from dotenv import load_dotenv
from extensions import mongo, mail, sess

load_dotenv()

def create_app(config_override=None):
    app = Flask(__name__)

    # ── Core config ──────────────────────────────────────────────────────────
    configured_secret = os.getenv('SECRET_KEY', '').strip()
    app.config['SECRET_KEY']          = configured_secret or 'development-only-secret'
    app.config['MONGO_URI']           = os.getenv('MONGO_URI', '')
    app.config['MISTRAL_API_KEY']     = os.getenv('MISTRAL_API_KEY', '')
    app.config['FALLBACK_STORAGE_MODE'] = os.getenv('FALLBACK_STORAGE_MODE', 'file')
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
    app.config['SESSION_TYPE']        = 'filesystem'
    app.config['SESSION_PERMANENT']   = False
    if config_override:
        app.config.update(config_override)

    # ── Init extensions ───────────────────────────────────────────────────────
    mongo.init_app(app)
    mail.init_app(app)
    sess.init_app(app)
    app.config['DEPENDENCY_STATUS'] = {
        'configuration': {
            'valid': bool(configured_secret),
            'warnings': [] if configured_secret else
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

    @app.get('/api/status')
    def status():
        return {
            'success': True,
            'dependencies': app.config['DEPENDENCY_STATUS'],
        }

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
