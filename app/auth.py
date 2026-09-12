from functools import wraps
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, jwt_required
from sqlalchemy.exc import IntegrityError
from .extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def body_fields(*fields):
    data = request.get_json(silent=True) or {}
    missing = [field for field in fields if not str(data.get(field, "")).strip()]
    return data, missing


def admin_required(function):
    @wraps(function)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if get_jwt().get("role") != "ADMIN":
            return jsonify(error="Acesso permitido somente ao administrador."), 403
        return function(*args, **kwargs)
    return wrapper


@auth_bp.post("/bootstrap")
def bootstrap_admin():
    if db.session.execute(db.select(User.id).limit(1)).first():
        return jsonify(error="O administrador inicial já foi cadastrado."), 409
    data, missing = body_fields("name", "password")
    if missing:
        return jsonify(error="Nome e senha são obrigatórios."), 400
    if len(data["password"]) < 8:
        return jsonify(error="A senha deve possuir pelo menos 8 caracteres."), 400
    user = User(name=data["name"].strip(), role="ADMIN")
    user.set_password(data["password"])
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Nome de usuário já utilizado."), 409
    return jsonify(user=user.to_dict()), 201


@auth_bp.post("/login")
def login():
    data, missing = body_fields("name", "password")
    if missing:
        return jsonify(error="Nome e senha são obrigatórios."), 400
    user = db.session.scalar(db.select(User).where(User.name == data["name"].strip()))
    if not user or not user.active or not user.check_password(data["password"]):
        return jsonify(error="Usuário ou senha inválidos."), 401
    token = create_access_token(identity=str(user.id),
                                additional_claims={"role": user.role})
    return jsonify(accessToken=token, user=user.to_dict())

