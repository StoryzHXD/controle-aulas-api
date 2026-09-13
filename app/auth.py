from datetime import timedelta, timezone
from functools import wraps
from secrets import randbelow

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from .email_service import send_verification_email
from .extensions import db
from .models import User, utc_now


auth_bp = Blueprint(
    "auth",
    __name__,
    url_prefix="/api/auth",
)

CODE_TTL = timedelta(minutes=10)
RESEND_INTERVAL = timedelta(seconds=60)
MAX_ATTEMPTS = 5


def as_utc(value):
    if value is None or value.tzinfo is not None:
        return value

    return value.replace(tzinfo=timezone.utc)


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


def new_verification_code(user):
    code = f"{randbelow(1_000_000):06d}"
    now = utc_now()

    user.verification_code_hash = (
        generate_password_hash(code)
    )

    user.verification_expires_at = (
        now + CODE_TTL
    )

    user.verification_attempts = 0
    user.verification_last_sent_at = now

    return code


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

        user = db.session.get(
            User,
            user_id,
        )

        if (
            user is None
            or not user.active
            or not user.email_verified
        ):
            return jsonify(
                error=(
                    "Usuário inativo, não confirmado "
                    "ou não encontrado."
                )
            ), 401

        if (
            user.role != "ADMIN"
            or user.father_id is not None
        ):
            return jsonify(
                error=(
                    "Acesso permitido somente ao "
                    "administrador principal."
                )
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
            error=(
                "Nome, e-mail e senha "
                "são obrigatórios."
            ),
            missing=missing,
        ), 400

    name = str(data["name"]).strip()
    email = normalize_email(data["email"])
    password = str(data["password"])

    if len(name) < 3:
        return jsonify(
            error=(
                "O nome deve possuir pelo menos "
                "3 caracteres."
            )
        ), 400

    if len(password) < 4:
        return jsonify(
            error=(
                "A senha deve possuir pelo menos "
                "4 caracteres."
            )
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
        email_verified=False,
    )

    user.set_password(password)

    verification_code = (
        new_verification_code(user)
    )

    db.session.add(user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Este e-mail já está cadastrado."
        ), 409

    email_sent = True

    try:
        send_verification_email(
            recipient=user.email,
            name=user.name,
            code=verification_code,
        )
    except Exception:
        email_sent = False

        # Como o envio falhou, o usuário
        # poderá tentar reenviar imediatamente.
        user.verification_last_sent_at = None

        db.session.commit()

        current_app.logger.exception(
            "Falha ao enviar o código de "
            "verificação para o usuário %s.",
            user.id,
        )

    return jsonify(
        message=(
            "Código de confirmação enviado."
            if email_sent
            else (
                "A conta foi criada, mas o código "
                "não pôde ser enviado. "
                "Tente reenviar."
            )
        ),
        verificationRequired=True,
        emailSent=email_sent,
        email=user.email,
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
            error=(
                "A conta não possui um "
                "administrador responsável."
            )
        ), 401

    if not user.email_verified:
        return jsonify(
            error="Confirme seu e-mail para entrar.",
            verificationRequired=True,
            email=user.email,
        ), 428

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
    ), 200


@auth_bp.post("/verify-email")
def verify_email():
    data, missing = body_fields(
        "email",
        "code",
    )

    if missing:
        return jsonify(
            error=(
                "E-mail e código são obrigatórios."
            )
        ), 400

    email = normalize_email(data["email"])
    code = str(data["code"]).strip()

    user = db.session.scalar(
        db.select(User).where(
            func.lower(User.email) == email
        )
    )

    if user is None:
        return jsonify(
            error="Código inválido ou expirado."
        ), 400

    if user.email_verified:
        token = create_user_token(user)

        return jsonify(
            access_token=token,
            user=user.to_dict(),
        ), 200

    if (
        user.verification_attempts
        >= MAX_ATTEMPTS
    ):
        return jsonify(
            error=(
                "Limite de tentativas atingido. "
                "Reenvie o código."
            )
        ), 429

    expires_at = as_utc(
        user.verification_expires_at
    )

    if (
        expires_at is None
        or expires_at < utc_now()
    ):
        return jsonify(
            error=(
                "Código expirado. "
                "Solicite um novo código."
            )
        ), 400

    valid_code = (
        user.verification_code_hash
        and check_password_hash(
            user.verification_code_hash,
            code,
        )
    )

    if not valid_code:
        user.verification_attempts += 1
        db.session.commit()

        return jsonify(
            error="Código inválido."
        ), 400

    user.email_verified = True
    user.verification_code_hash = None
    user.verification_expires_at = None
    user.verification_attempts = 0
    user.verification_last_sent_at = None

    db.session.commit()

    token = create_user_token(user)

    return jsonify(
        access_token=token,
        user=user.to_dict(),
    ), 200


@auth_bp.post("/resend-verification")
def resend_verification():
    data, missing = body_fields("email")

    if missing:
        return jsonify(
            error="Informe o e-mail."
        ), 400

    email = normalize_email(data["email"])

    user = db.session.scalar(
        db.select(User).where(
            func.lower(User.email) == email
        )
    )

    generic_message = (
        "Se existir uma conta pendente, "
        "um novo código será enviado."
    )

    if (
        user is None
        or user.email_verified
        or not user.active
    ):
        return jsonify(
            message=generic_message
        ), 200

    now = utc_now()

    last_sent = as_utc(
        user.verification_last_sent_at
    )

    if (
        last_sent
        and now - last_sent < RESEND_INTERVAL
    ):
        elapsed = int(
            (now - last_sent).total_seconds()
        )

        remaining = 60 - elapsed

        return jsonify(
            error=(
                f"Aguarde {max(1, remaining)} "
                "segundos para reenviar."
            )
        ), 429

    code = new_verification_code(user)
    db.session.commit()

    try:
        send_verification_email(
            recipient=user.email,
            name=user.name,
            code=code,
        )
    except Exception:
        # Não aplica o intervalo de reenvio
        # quando a mensagem não foi enviada.
        user.verification_last_sent_at = None

        db.session.commit()

        current_app.logger.exception(
            "Falha ao reenviar código de "
            "verificação para o usuário %s.",
            user.id,
        )

        return jsonify(
            error=(
                "Não foi possível enviar o código. "
                "Verifique a configuração do Brevo."
            )
        ), 503

    return jsonify(
        message=generic_message
    ), 200