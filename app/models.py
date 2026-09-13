from datetime import date, datetime, time, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from .auth import (
    admin_required,
    body_fields,
    normalize_email,
)
from .extensions import db
from .models import (
    Notification,
    Room,
    Schedule,
    User,
    SHIFTS,
    SCHEDULE_STATUSES,
)


api_bp = Blueprint(
    "api",
    __name__,
    url_prefix="/api",
)


def current_school_id():
    """
    Obtém o ID da escola armazenado no JWT.
    """
    school_id = get_jwt().get("school_id")

    try:
        return int(school_id)
    except (TypeError, ValueError):
        return None


def current_user():
    """
    Retorna o usuário autenticado somente se ele pertencer
    à escola presente no JWT.
    """
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None

    school_id = current_school_id()

    if school_id is None:
        return None

    return db.session.scalar(
        db.select(User).where(
            User.id == user_id,
            User.school_id == school_id,
        )
    )


def find_in_school(model, item_id):
    """
    Busca um registro pelo ID, garantindo que pertença
    à escola do usuário autenticado.
    """
    school_id = current_school_id()

    if school_id is None:
        return None

    return db.session.scalar(
        db.select(model).where(
            model.id == item_id,
            model.school_id == school_id,
        )
    )


def valid_shift(value):
    return str(value).strip().upper() in SHIFTS


def notify(user_id, title, message):
    """
    Cria uma notificação vinculada à escola atual.
    O commit é realizado pela função que chamou notify().
    """
    school_id = current_school_id()

    if school_id is None:
        return

    db.session.add(
        Notification(
            school_id=school_id,
            user_id=user_id,
            title=title,
            message=message,
        )
    )


def invalid_session_response():
    return jsonify(
        error="Sessão inválida ou sem escola vinculada."
    ), 401


@api_bp.get("/health")
def health():
    return jsonify(
        status="ok",
        version="3.0",
    )


@api_bp.get("/me")
@jwt_required()
def me():
    user = current_user()

    if user is None or not user.active:
        return jsonify(
            error="Usuário inativo ou sessão inválida."
        ), 401

    return jsonify(
        user=user.to_dict()
    )


# =========================================================
# PROFESSORES
# =========================================================

@api_bp.get("/teachers")
@admin_required
def list_teachers():
    school_id = current_school_id()

    if school_id is None:
        return invalid_session_response()

    items = db.session.scalars(
        db.select(User)
        .where(
            User.school_id == school_id,
            User.role == "PROFESSOR",
        )
        .order_by(User.name)
    ).all()

    return jsonify(
        items=[item.to_dict() for item in items]
    )


@api_bp.post("/teachers")
@admin_required
def create_teacher():
    school_id = current_school_id()

    if school_id is None:
        return invalid_session_response()

    data, missing = body_fields(
        "name",
        "email",
        "password",
        "subject",
        "shift",
    )

    if missing:
        return jsonify(
            error=(
                "Nome, e-mail, senha, disciplina "
                "e turno são obrigatórios."
            ),
            missing=missing,
        ), 400

    name = str(data["name"]).strip()
    email = normalize_email(data["email"])
    password = str(data["password"])
    subject = str(data["subject"]).strip()
    shift = str(data["shift"]).strip().upper()

    if len(name) < 3:
        return jsonify(
            error="O nome deve possuir pelo menos 3 caracteres."
        ), 400

    if not valid_shift(shift):
        return jsonify(
            error="Turno deve ser MANHA, TARDE ou NOITE."
        ), 400

    if len(password) < 8:
        return jsonify(
            error="A senha deve possuir pelo menos 8 caracteres."
        ), 400

    teacher = User(
        school_id=school_id,
        name=name,
        email=email,
        subject=subject,
        shift=shift,
        role="PROFESSOR",
        active=True,
    )

    teacher.set_password(password)

    db.session.add(teacher)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Este e-mail já está sendo usado nesta escola."
        ), 409

    return jsonify(
        teacher=teacher.to_dict()
    ), 201


@api_bp.patch("/teachers/<int:teacher_id>")
@admin_required
def update_teacher(teacher_id):
    teacher = find_in_school(User, teacher_id)

    if teacher is None or teacher.role != "PROFESSOR":
        return jsonify(
            error="Professor não encontrado."
        ), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = str(data.get("name", "")).strip()

        if len(name) < 3:
            return jsonify(
                error="O nome deve possuir pelo menos 3 caracteres."
            ), 400

        teacher.name = name

    if "email" in data:
        email = normalize_email(data.get("email", ""))

        if not email:
            return jsonify(
                error="O e-mail não pode ficar vazio."
            ), 400

        teacher.email = email

    if "subject" in data:
        subject = str(data.get("subject", "")).strip()

        if not subject:
            return jsonify(
                error="A disciplina não pode ficar vazia."
            ), 400

        teacher.subject = subject

    if "shift" in data:
        shift = str(data.get("shift", "")).strip().upper()

        if not valid_shift(shift):
            return jsonify(
                error="Turno inválido."
            ), 400

        teacher.shift = shift

    if data.get("password"):
        password = str(data["password"])

        if len(password) < 8:
            return jsonify(
                error="A senha deve possuir pelo menos 8 caracteres."
            ), 400

        teacher.set_password(password)

    if "active" in data:
        teacher.active = bool(data["active"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Este e-mail já está sendo usado nesta escola."
        ), 409

    return jsonify(
        teacher=teacher.to_dict()
    )


# =========================================================
# SALAS
# =========================================================

@api_bp.get("/rooms")
@jwt_required()
def list_rooms():
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    query = db.select(Room).where(
        Room.school_id == user.school_id,
        Room.active.is_(True),
    )

    if user.role == "PROFESSOR":
        query = query.where(
            Room.shift == user.shift
        )

    items = db.session.scalars(
        query.order_by(Room.name)
    ).all()

    return jsonify(
        items=[item.to_dict() for item in items]
    )


@api_bp.post("/rooms")
@admin_required
def create_room():
    school_id = current_school_id()

    if school_id is None:
        return invalid_session_response()

    data, missing = body_fields(
        "name",
        "shift",
        "lessonCount",
    )

    if missing:
        return jsonify(
            error=(
                "Nome, turno e quantidade "
                "de aulas são obrigatórios."
            ),
            missing=missing,
        ), 400

    name = str(data["name"]).strip()
    shift = str(data["shift"]).strip().upper()

    try:
        lesson_count = int(data["lessonCount"])
    except (TypeError, ValueError):
        return jsonify(
            error="Quantidade de aulas inválida."
        ), 400

    if len(name) < 2:
        return jsonify(
            error="O nome da sala deve possuir pelo menos 2 caracteres."
        ), 400

    if not valid_shift(shift):
        return jsonify(
            error="Turno deve ser MANHA, TARDE ou NOITE."
        ), 400

    if not 7 <= lesson_count <= 16:
        return jsonify(
            error="Use uma quantidade de aulas entre 7 e 16."
        ), 400

    room = Room(
        school_id=school_id,
        name=name,
        shift=shift,
        lesson_count=lesson_count,
        active=True,
    )

    db.session.add(room)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Já existe uma sala com esse nome nesta escola."
        ), 409

    return jsonify(
        room=room.to_dict()
    ), 201


@api_bp.patch("/rooms/<int:room_id>")
@admin_required
def update_room(room_id):
    room = find_in_school(Room, room_id)

    if room is None:
        return jsonify(
            error="Sala não encontrada."
        ), 404

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = str(data.get("name", "")).strip()

        if len(name) < 2:
            return jsonify(
                error="O nome da sala deve possuir pelo menos 2 caracteres."
            ), 400

        room.name = name

    if "shift" in data:
        shift = str(data.get("shift", "")).strip().upper()

        if not valid_shift(shift):
            return jsonify(
                error="Turno inválido."
            ), 400

        room.shift = shift

    if "lessonCount" in data:
        try:
            lesson_count = int(data["lessonCount"])
        except (TypeError, ValueError):
            return jsonify(
                error="Quantidade de aulas inválida."
            ), 400

        if not 7 <= lesson_count <= 16:
            return jsonify(
                error="Use uma quantidade de aulas entre 7 e 16."
            ), 400

        room.lesson_count = lesson_count

    if "active" in data:
        room.active = bool(data["active"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Já existe uma sala com esse nome nesta escola."
        ), 409

    return jsonify(
        room=room.to_dict()
    )


# =========================================================
# AGENDAMENTOS
# =========================================================

@api_bp.get("/rooms/<int:room_id>/schedules")
@jwt_required()
def list_schedules(room_id):
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    room = find_in_school(Room, room_id)

    if room is None:
        return jsonify(
            error="Sala não encontrada."
        ), 404

    if (
        user.role == "PROFESSOR"
        and room.shift != user.shift
    ):
        return jsonify(
            error="Você não possui acesso às salas de outro turno."
        ), 403

    start_value = request.args.get(
        "start",
        date.today().isoformat(),
    )

    end_value = request.args.get(
        "end",
        start_value,
    )

    try:
        start_date = date.fromisoformat(start_value)
        end_date = date.fromisoformat(end_value)
    except (TypeError, ValueError):
        return jsonify(
            error="Use datas no formato AAAA-MM-DD."
        ), 400

    if end_date < start_date:
        return jsonify(
            error="A data final não pode ser anterior à data inicial."
        ), 400

    query = db.select(Schedule).where(
        Schedule.school_id == user.school_id,
        Schedule.room_id == room.id,
        Schedule.class_date.between(
            start_date,
            end_date,
        ),
    )

    items = db.session.scalars(
        query.order_by(
            Schedule.class_date,
            Schedule.lesson_number,
        )
    ).all()

    return jsonify(
        room=room.to_dict(),
        items=[item.to_dict() for item in items],
    )


@api_bp.post("/rooms/<int:room_id>/schedules")
@jwt_required()
def create_schedule(room_id):
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    if user.role != "PROFESSOR":
        return jsonify(
            error="Somente professores podem agendar aulas."
        ), 403

    room = find_in_school(Room, room_id)

    if room is None or not room.active:
        return jsonify(
            error="Sala não encontrada."
        ), 404

    if room.shift != user.shift:
        return jsonify(
            error="Você só pode agendar salas do seu turno."
        ), 403

    data, missing = body_fields(
        "date",
        "lessonNumber",
        "time",
    )

    if missing:
        return jsonify(
            error="Data, aula e horário são obrigatórios.",
            missing=missing,
        ), 400

    try:
        class_date = date.fromisoformat(
            str(data["date"])
        )

        lesson_number = int(
            data["lessonNumber"]
        )

        class_time = time.fromisoformat(
            str(data["time"])
        )
    except (TypeError, ValueError):
        return jsonify(
            error="Dados de agendamento inválidos."
        ), 400

    if class_date < date.today():
        return jsonify(
            error="Não é possível agendar uma aula em uma data passada."
        ), 400

    if not 1 <= lesson_number <= room.lesson_count:
        return jsonify(
            error="Número de aula inválido para esta sala."
        ), 400

    schedule = Schedule(
        school_id=user.school_id,
        room_id=room.id,
        teacher_id=user.id,
        class_date=class_date,
        lesson_number=lesson_number,
        class_time=class_time,
        status="AGENDADA",
    )

    db.session.add(schedule)

    try:
        db.session.flush()

        admins = db.session.scalars(
            db.select(User).where(
                User.school_id == user.school_id,
                User.role == "ADMIN",
                User.active.is_(True),
            )
        ).all()

        for admin in admins:
            notify(
                admin.id,
                "Nova aula agendada",
                (
                    f"{user.name} agendou a sala "
                    f"{room.name} para {class_date.strftime('%d/%m/%Y')} "
                    f"às {class_time.strftime('%H:%M')}."
                ),
            )

        db.session.commit()

    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Essa aula já está ocupada."
        ), 409

    return jsonify(
        schedule=schedule.to_dict()
    ), 201


@api_bp.patch("/schedules/<int:schedule_id>/status")
@admin_required
def update_schedule_status(schedule_id):
    schedule = find_in_school(
        Schedule,
        schedule_id,
    )

    if schedule is None:
        return jsonify(
            error="Agendamento não encontrado."
        ), 404

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip().upper()

    if status not in SCHEDULE_STATUSES:
        return jsonify(
            error="Status inválido."
        ), 400

    schedule.status = status

    if status == "CANCELADA":
        schedule.cancelled_by_id = int(
            get_jwt_identity()
        )

        schedule.cancelled_at = datetime.now(
            timezone.utc
        )
    else:
        schedule.cancelled_by_id = None
        schedule.cancelled_at = None

    notify(
        schedule.teacher_id,
        "Status da aula alterado",
        (
            f"A aula na sala {schedule.room.name} "
            f"agora está {status}."
        ),
    )

    db.session.commit()

    return jsonify(
        schedule=schedule.to_dict()
    )


@api_bp.delete("/schedules/<int:schedule_id>")
@jwt_required()
def cancel_schedule(schedule_id):
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    schedule = find_in_school(
        Schedule,
        schedule_id,
    )

    if schedule is None:
        return jsonify(
            error="Agendamento não encontrado."
        ), 404

    if (
        user.role != "ADMIN"
        and schedule.teacher_id != user.id
    ):
        return jsonify(
            error="Você não pode cancelar esta aula."
        ), 403

    schedule.status = "CANCELADA"
    schedule.cancelled_by_id = user.id
    schedule.cancelled_at = datetime.now(
        timezone.utc
    )

    if user.role == "PROFESSOR":
        admins = db.session.scalars(
            db.select(User).where(
                User.school_id == user.school_id,
                User.role == "ADMIN",
                User.active.is_(True),
            )
        ).all()

        for admin in admins:
            notify(
                admin.id,
                "Aula cancelada",
                (
                    f"{user.name} cancelou a aula na sala "
                    f"{schedule.room.name}."
                ),
            )

    elif schedule.teacher_id != user.id:
        notify(
            schedule.teacher_id,
            "Aula cancelada",
            (
                f"A aula na sala {schedule.room.name} "
                "foi cancelada pelo administrador."
            ),
        )

    db.session.commit()

    return jsonify(
        schedule=schedule.to_dict()
    )


# =========================================================
# NOTIFICAÇÕES
# =========================================================

@api_bp.get("/notifications")
@jwt_required()
def list_notifications():
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    items = db.session.scalars(
        db.select(Notification)
        .where(
            Notification.school_id == user.school_id,
            Notification.user_id == user.id,
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).all()

    unread_count = db.session.scalar(
        db.select(
            func.count(Notification.id)
        ).where(
            Notification.school_id == user.school_id,
            Notification.user_id == user.id,
            Notification.read.is_(False),
        )
    ) or 0

    return jsonify(
        unreadCount=unread_count,
        items=[item.to_dict() for item in items],
    )


@api_bp.patch(
    "/notifications/<int:notification_id>/read"
)
@jwt_required()
def read_notification(notification_id):
    user = current_user()

    if user is None or not user.active:
        return invalid_session_response()

    notification = db.session.scalar(
        db.select(Notification).where(
            Notification.id == notification_id,
            Notification.school_id == user.school_id,
            Notification.user_id == user.id,
        )
    )

    if notification is None:
        return jsonify(
            error="Notificação não encontrada."
        ), 404

    notification.read = True
    db.session.commit()

    return jsonify(
        notification=notification.to_dict()
    )