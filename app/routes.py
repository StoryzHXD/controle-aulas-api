from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
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

APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def local_now():
    return datetime.now(APP_TIMEZONE)


def local_today():
    return local_now().date()


def scheduling_window_is_open(moment=None):
    moment = moment or local_now()
    weekday = moment.weekday()

    # Python:
    # segunda = 0
    # sexta = 4
    # sábado = 5
    # domingo = 6

    if weekday == 5:
        return False

    if weekday == 6:
        opening_time = time(
            hour=0,
            minute=1
        )

        return moment.time().replace(
            tzinfo=None
        ) >= opening_time

    return True


def is_school_day(class_date):
    return class_date.weekday() in range(0, 5)

def current_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        return None

    return db.session.get(User, user_id)


def current_owner_id(user=None):
    user = user or current_user()

    if user is None:
        return None

    if user.role == "ADMIN":
        return user.id

    return user.father_id


def find_for_owner(model, item_id, owner_id=None):
    owner_id = owner_id or current_owner_id()

    if owner_id is None:
        return None

    return db.session.scalar(
        db.select(model).where(
            model.id == item_id,
            model.father_id == owner_id,
        )
    )


def valid_shift(value):
    return str(value).strip().upper() in SHIFTS


def invalid_session_response():
    return jsonify(
        error="Sessão inválida ou usuário sem administrador responsável."
    ), 401


def notify(owner_id, user_id, title, message):
    db.session.add(
        Notification(
            father_id=owner_id,
            user_id=user_id,
            title=title,
            message=message,
        )
    )


@api_bp.get("/health")
def health():
    return jsonify(
        status="ok",
        version="4.0",
    )


@api_bp.get("/me")
@jwt_required()
def me():
    user = current_user()

    if user is None or not user.active:
        return jsonify(
            error="Usuário inativo ou sessão inválida."
        ), 401

    if current_owner_id(user) is None:
        return invalid_session_response()

    return jsonify(
        user=user.to_dict()
    )


# =========================================================
# PROFESSORES
# =========================================================

@api_bp.get("/teachers")
@admin_required
def list_teachers():
    admin = current_user()

    items = db.session.scalars(
        db.select(User)
        .where(
            User.father_id == admin.id,
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
    admin = current_user()

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
        father_id=admin.id,
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
            error="Este e-mail já está cadastrado."
        ), 409

    return jsonify(
        teacher=teacher.to_dict()
    ), 201


@api_bp.patch("/teachers/<int:teacher_id>")
@admin_required
def update_teacher(teacher_id):
    admin = current_user()

    teacher = db.session.scalar(
        db.select(User).where(
            User.id == teacher_id,
            User.father_id == admin.id,
            User.role == "PROFESSOR",
        )
    )

    if teacher is None:
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
            error="Este e-mail já está cadastrado."
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
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    query = db.select(Room).where(
        Room.father_id == owner_id,
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
    admin = current_user()

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
        father_id=admin.id,
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
            error="Já existe uma sala com esse nome para este administrador."
        ), 409

    return jsonify(
        room=room.to_dict()
    ), 201


@api_bp.patch("/rooms/<int:room_id>")
@admin_required
def update_room(room_id):
    admin = current_user()
    room = find_for_owner(Room, room_id, admin.id)

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
                error="Use uma quantidade entre 7 e 16."
            ), 400

        room.lesson_count = lesson_count

    if "active" in data:
        room.active = bool(data["active"])

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

        return jsonify(
            error="Já existe uma sala com esse nome."
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
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    room = find_for_owner(
        Room,
        room_id,
        owner_id,
    )

    if room is None:
        return jsonify(
            error="Sala não encontrada."
        ), 404

    if (
        user.role == "PROFESSOR"
        and room.shift != user.shift
    ):
        return jsonify(
            error="Sala pertencente a outro turno."
        ), 403

    start_value = request.args.get(
        "start",
        local_today().isoformat(),
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
            error="A data final não pode ser anterior à inicial."
        ), 400

    items = db.session.scalars(
        db.select(Schedule)
        .where(
            Schedule.father_id == owner_id,
            Schedule.room_id == room.id,
            Schedule.class_date.between(
                start_date,
                end_date,
            ),
        )
        .order_by(
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
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    if user.role != "PROFESSOR":
        return jsonify(
            error="Somente professores podem agendar."
        ), 403

    if not scheduling_window_is_open():
        return jsonify(
            error=(
                "Novos agendamentos ficam indisponíveis "
                "aos sábados e são liberados no domingo "
                "a partir de 00:01."
            )
        ), 400

    room = find_for_owner(
        Room,
        room_id,
        owner_id,
    )

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

    if not is_school_day(class_date):
        return jsonify(
            error=(
                "As aulas só podem ser agendadas "
                "de segunda a sexta-feira."
            )
        ), 400

    now = local_now()
    today = now.date()

    if class_date < today:
        return jsonify(
            error="Não é possível agendar uma data passada."
        ), 400

    if class_date == today:
        scheduled_moment = datetime.combine(
            class_date,
            class_time,
            tzinfo=APP_TIMEZONE,
        )

        if scheduled_moment <= now:
            return jsonify(
                error=(
                    "Este horário já passou e não pode "
                    "mais ser agendado."
                )
            ), 400

    if not 1 <= lesson_number <= room.lesson_count:
        return jsonify(
            error="Número de aula inválido."
        ), 400

    schedule = Schedule(
        father_id=owner_id,
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

        notify(
            owner_id=owner_id,
            user_id=owner_id,
            title="Nova aula agendada",
            message=(
                f"{user.name} agendou a sala "
                f"{room.name} para "
                f"{class_date.strftime('%d/%m/%Y')} "
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
    admin = current_user()

    schedule = find_for_owner(
        Schedule,
        schedule_id,
        admin.id,
    )

    if schedule is None:
        return jsonify(
            error="Agendamento não encontrado."
        ), 404

    data = request.get_json(silent=True) or {}
    status = str(
        data.get("status", "")
    ).strip().upper()

    if status not in SCHEDULE_STATUSES:
        return jsonify(
            error="Status inválido."
        ), 400

    schedule.status = status

    if status == "CANCELADA":
        schedule.cancelled_by_id = admin.id
        schedule.cancelled_at = datetime.now(
            timezone.utc
        )
    else:
        schedule.cancelled_by_id = None
        schedule.cancelled_at = None

    notify(
        owner_id=admin.id,
        user_id=schedule.teacher_id,
        title="Status da aula alterado",
        message=(
            f"A aula em {schedule.room.name} "
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
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    schedule = find_for_owner(
        Schedule,
        schedule_id,
        owner_id,
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
            error="Você não pode remover este agendamento."
        ), 403

    removed_schedule_id = schedule.id
    teacher_id = schedule.teacher_id
    room_name = schedule.room.name
    teacher_name = schedule.teacher.name

    if user.role == "PROFESSOR":
        notify(
            owner_id=owner_id,
            user_id=owner_id,
            title="Agendamento removido",
            message=(
                f"{teacher_name} desagendou a aula "
                f"na sala {room_name}."
            ),
        )

    elif teacher_id != user.id:
        notify(
            owner_id=owner_id,
            user_id=teacher_id,
            title="Agendamento removido",
            message=(
                f"O administrador removeu seu "
                f"agendamento na sala {room_name}."
            ),
        )

    db.session.delete(schedule)
    db.session.commit()

    return jsonify(
        message="Agendamento removido com sucesso.",
        scheduleId=removed_schedule_id,
    ), 200


# =========================================================
# NOTIFICAÇÕES
# =========================================================

@api_bp.get("/notifications")
@jwt_required()
def list_notifications():
    user = current_user()
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    items = db.session.scalars(
        db.select(Notification)
        .where(
            Notification.father_id == owner_id,
            Notification.user_id == user.id,
        )
        .order_by(
            Notification.created_at.desc()
        )
        .limit(50)
    ).all()

    unread_count = db.session.scalar(
        db.select(
            func.count(Notification.id)
        ).where(
            Notification.father_id == owner_id,
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
    owner_id = current_owner_id(user)

    if (
        user is None
        or not user.active
        or owner_id is None
    ):
        return invalid_session_response()

    notification = db.session.scalar(
        db.select(Notification).where(
            Notification.id == notification_id,
            Notification.father_id == owner_id,
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