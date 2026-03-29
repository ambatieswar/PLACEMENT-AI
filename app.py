import os
from flask import Flask
from dotenv import load_dotenv
from extensions import mongo, mail, sess

load_dotenv()

def create_app():
    app = Flask(__name__)

    # ── Core config ──────────────────────────────────────────────────────────
    app.config['SECRET_KEY']          = os.getenv('SECRET_KEY', 'change-me-in-production')
    app.config['MONGO_URI']           = os.getenv('MONGO_URI', 'mongodb://localhost:27017/placementai')

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

    # ── Init extensions ───────────────────────────────────────────────────────
    mongo.init_app(app)
    mail.init_app(app)
    sess.init_app(app)

    # ── Register blueprints ───────────────────────────────────────────────────
    from routes.auth      import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.features  import features_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(features_bp)

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
