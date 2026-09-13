from functools import wraps
from secrets import token_hex

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    jwt_required,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import School, User


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


def normalize_school_code(value):
    return (
        str(value)
        .strip()
        .upper()
        .replace(" ", "")
    )


def generate_school_code():
    """
    Gera códigos como ESC-A1B2C3D4.
    Continua tentando até encontrar um código não utilizado.
    """
    while True:
        code = f"ESC-{token_hex(4).upper()}"

        existing_school = db.session.scalar(
            db.select(School.id).where(
                School.code == code
            )
        )

        if existing_school is None:
            return code


def create_user_token(user):
    return create_access_token(
        identity=str(user.id),
        additional_claims={
            "role": user.role,
            "shift": user.shift,
            "school_id": user.school_id,
        },
    )


def get_current_school_id():
    return get_jwt().get("school_id")


def admin_required(function):
    @wraps(function)
    @jwt_required()
    def wrapper(*args, **kwargs):
        claims = get_jwt()

        if claims.get("role") != "ADMIN":
            return jsonify(
                error=(
                    "Acesso permitido somente "
                    "ao administrador."
                )
            ), 403

        if claims.get("school_id") is None:
            return jsonify(
                error="A sessão não possui uma escola vinculada."
            ), 401

        return function(*args, **kwargs)

    return wrapper


@auth_bp.post("/bootstrap")
def bootstrap_admin():
    """
    Cria uma nova escola e o administrador responsável.

    Cada chamada cria uma escola diferente. Portanto, não existe
    mais a limitação de apenas um administrador no sistema inteiro.

    JSON esperado:
    {
        "school_name": "Escola Exemplo",
        "name": "Administrador",
        "email": "admin@escola.com",
        "password": "1234"
    }
    """
    data, missing = body_fields(
        "school_name",
        "name",
        "email",
        "password",
    )

    if missing:
        return jsonify(
            error=(
                "Nome da escola, nome do administrador, "
                "e-mail e senha são obrigatórios."
            ),
            missing=missing,
        ), 400

    school_name = str(data["school_name"]).strip()
    admin_name = str(data["name"]).strip()
    email = normalize_email(data["email"])
    password = str(data["password"])

    if len(school_name) < 3:
        return jsonify(
            error=(
                "O nome da escola deve possuir "
                "pelo menos 3 caracteres."
            )
        ), 400

    if len(admin_name) < 3:
        return jsonify(
            error=(
                "O nome do administrador deve possuir "
                "pelo menos 3 caracteres."
            )
        ), 400

    if len(password) < 4:
        return jsonify(
            error=(
                "A senha deve possuir "
                "pelo menos 4 caracteres."
            )
        ), 400

    school = School(
        name=school_name,
        code=generate_school_code(),
    )

    db.session.add(school)

    try:
        # Obtém school.id sem confirmar a transação.
        db.session.flush()

        user = User(
            school_id=school.id,
            name=admin_name,
            email=email,
            role="ADMIN",
            shift=None,
            active=True,
        )

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error=(
                "Não foi possível criar a escola. "
                "Verifique se os dados já estão cadastrados."
            )
        ), 409

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
        school=school.to_dict(),
    ), 201


@auth_bp.post("/login")
def login():
    """
    Login isolado por escola.

    JSON esperado:
    {
        "school_code": "ESC-A1B2C3D4",
        "email": "admin@escola.com",
        "password": "1234"
    }
    """
    data, missing = body_fields(
        "school_code",
        "email",
        "password",
    )

    if missing:
        return jsonify(
            error=(
                "Código da escola, e-mail "
                "e senha são obrigatórios."
            ),
            missing=missing,
        ), 400

    school_code = normalize_school_code(
        data["school_code"]
    )

    email = normalize_email(data["email"])
    password = str(data["password"])

    school = db.session.scalar(
        db.select(School).where(
            func.upper(School.code) == school_code
        )
    )

    if school is None or not school.active:
        return jsonify(
            error="Código da escola inválido."
        ), 401

    user = db.session.scalar(
        db.select(User).where(
            User.school_id == school.id,
            func.lower(User.email) == email,
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

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
        school=school.to_dict(),
    ), 200