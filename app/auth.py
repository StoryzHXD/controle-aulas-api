from functools import wraps

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth",
)


def body_fields(*fields):
    data = request.get_json(silent=True) or {}

    missing = [
        field
        for field in fields
        if not str(data.get(field, "")).strip()
    ]

    return data, missing


def normalize_email(value):
    return str(value).strip().lower()


def create_user_token(user):
    return create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "shift": user.shift,
            "father_id": user.father_id,
            "owner_id": user.owner_id(),
        },
    )


def admin_required(function):
    @wraps(function)
    @jwt_required()
    def wrapper(*args, **kwargs):
        try:
            user_id = int(get_jwt_identity())
        except (TypeError, ValueError):
            return jsonify(
                error="Sessão inválida."
            ), 401

        user = db.session.get(User, user_id)

        if user is None or not user.active:
            return jsonify(
                error="Usuário inativo ou não encontrado."
            ), 401

        if user.role != "ADMIN":
            return jsonify(
                error="Acesso permitido somente ao administrador."
            ), 403

        if user.father_id is not None:
            return jsonify(
                error="Administrador principal inválido."
            ), 403

        return function(*args, **kwargs)

    return wrapper


@auth_bp.post("/bootstrap")
def bootstrap_admin():
    data, missing = body_fields(
        "name",
        "email",
        "password",
    )

    if missing:
        return jsonify(
            error="Nome, e-mail e senha são obrigatórios.",
            missing=missing,
        ), 400

    name = str(data["name"]).strip()
    email = normalize_email(data["email"])
    password = str(data["password"])

    if len(name) < 3:
        return jsonify(
            error="O nome deve possuir pelo menos 3 caracteres."
        ), 400

    if len(password) < 4:
        return jsonify(
            error="A senha deve possuir pelo menos 4 caracteres."
        ), 400

    existing_user = db.session.scalar(
        db.select(User.id).where(
            func.lower(User.email) == email
        )
    )

    if existing_user is not None:
        return jsonify(
            error="Este e-mail já está cadastrado."
        ), 409

    user = User(
        father_id=None,
        name=name,
        email=email,
        role="ADMIN",
        subject=None,
        shift=None,
        active=True,
    )

    user.set_password(password)
    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Este e-mail já está cadastrado."
        ), 409

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
    ), 201


@auth_bp.post("/login")
def login():
    data, missing = body_fields(
        "email",
        "password",
    )

    if missing:
        return jsonify(
            error="E-mail e senha são obrigatórios.",
            missing=missing,
        ), 400

    email = normalize_email(data["email"])
    password = str(data["password"])

    user = db.session.scalar(
        db.select(User).where(
            func.lower(User.email) == email
        )
    )

    if (
        user is None
        or not user.active
        or not user.check_password(password)
    ):
        return jsonify(
            error="E-mail ou senha inválidos."
        ), 401

    if (
        user.role == "PROFESSOR"
        and user.father_id is None
    ):
        return jsonify(
            error="A conta não possui um administrador responsável."
        ), 401

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
    ), 200