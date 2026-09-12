import os
from datetime import timedelta
from flask import Flask, jsonify
from .auth import auth_bp
from .extensions import cors, db, jwt, migrate
from .routes import api_bp


def create_app(test_config=None):
    app = Flask(__name__)
    database_url = os.getenv("DATABASE_URL", "sqlite:///controle_aulas.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
        JWT_SECRET_KEY=os.getenv("JWT_SECRET_KEY", "dev-only-change-me"),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(hours=8),
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    origins = os.getenv("FRONTEND_ORIGINS", "*").split(",")
    cors.init_app(app, resources={r"/api/*": {"origins": origins}})
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Rota não encontrada."), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return jsonify(error="Erro interno do servidor."), 500

    return app

