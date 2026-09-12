from datetime import date, datetime, time, timezone
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from .auth import admin_required, body_fields, normalize_email
from .extensions import db
from .models import Notification, Room, Schedule, User, SHIFTS, SCHEDULE_STATUSES

api_bp = Blueprint("api", __name__, url_prefix="/api")


def current_user(): return db.session.get(User, int(get_jwt_identity()))
def find(model, item_id): return db.session.get(model, item_id)
def valid_shift(value): return str(value).strip().upper() in SHIFTS
def notify(user_id, title, message):
    db.session.add(Notification(user_id=user_id, title=title, message=message))


@api_bp.get("/health")
def health(): return jsonify(status="ok", version="2.0")


@api_bp.get("/me")
@jwt_required()
def me():
    user = current_user()
    return jsonify(user=user.to_dict()) if user and user.active else (jsonify(error="Usuário inativo."), 401)


@api_bp.get("/teachers")
@admin_required
def list_teachers():
    items = db.session.scalars(db.select(User).where(User.role == "PROFESSOR").order_by(User.name)).all()
    return jsonify(items=[item.to_dict() for item in items])


@api_bp.post("/teachers")
@admin_required
def create_teacher():
    data, missing = body_fields("name", "email", "password", "subject", "shift")
    if missing: return jsonify(error="Nome, e-mail, senha, disciplina e turno são obrigatórios."), 400
    shift = str(data["shift"]).upper()
    if not valid_shift(shift): return jsonify(error="Turno deve ser MANHA, TARDE ou NOITE."), 400
    if len(data["password"]) < 8: return jsonify(error="A senha deve possuir pelo menos 8 caracteres."), 400
    teacher = User(name=data["name"].strip(), email=normalize_email(data["email"]),
                   subject=data["subject"].strip(), shift=shift, role="PROFESSOR")
    teacher.set_password(data["password"])
    db.session.add(teacher)
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback(); return jsonify(error="E-mail já utilizado."), 409
    return jsonify(teacher=teacher.to_dict()), 201


@api_bp.patch("/teachers/<int:teacher_id>")
@admin_required
def update_teacher(teacher_id):
    teacher = find(User, teacher_id)
    if not teacher or teacher.role != "PROFESSOR": return jsonify(error="Professor não encontrado."), 404
    data = request.get_json(silent=True) or {}
    if data.get("name"): teacher.name = str(data["name"]).strip()
    if data.get("email"): teacher.email = normalize_email(data["email"])
    if data.get("subject"): teacher.subject = str(data["subject"]).strip()
    if "shift" in data:
        if not valid_shift(data["shift"]): return jsonify(error="Turno inválido."), 400
        teacher.shift = str(data["shift"]).upper()
    if data.get("password"):
        if len(data["password"]) < 8: return jsonify(error="Senha muito curta."), 400
        teacher.set_password(data["password"])
    if "active" in data: teacher.active = bool(data["active"])
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback(); return jsonify(error="E-mail já utilizado."), 409
    return jsonify(teacher=teacher.to_dict())


@api_bp.get("/rooms")
@jwt_required()
def list_rooms():
    query = db.select(Room).where(Room.active.is_(True))
    user = current_user()
    if user.role == "PROFESSOR": query = query.where(Room.shift == user.shift)
    items = db.session.scalars(query.order_by(Room.name)).all()
    return jsonify(items=[item.to_dict() for item in items])


@api_bp.post("/rooms")
@admin_required
def create_room():
    data, missing = body_fields("name", "shift", "lessonCount")
    if missing: return jsonify(error="Nome, turno e quantidade de aulas são obrigatórios."), 400
    shift = str(data["shift"]).upper()
    try: count = int(data["lessonCount"])
    except (TypeError, ValueError): return jsonify(error="Quantidade inválida."), 400
    if not valid_shift(shift) or not 7 <= count <= 16:
        return jsonify(error="Use turno válido e quantidade entre 7 e 16."), 400
    room = Room(name=data["name"].strip(), shift=shift, lesson_count=count)
    db.session.add(room)
    try: db.session.commit()
    except IntegrityError:
        db.session.rollback(); return jsonify(error="Já existe uma sala com esse nome."), 409
    return jsonify(room=room.to_dict()), 201


@api_bp.patch("/rooms/<int:room_id>")
@admin_required
def update_room(room_id):
    room = find(Room, room_id)
    if not room: return jsonify(error="Sala não encontrada."), 404
    data = request.get_json(silent=True) or {}
    if data.get("name"): room.name = str(data["name"]).strip()
    if "shift" in data:
        if not valid_shift(data["shift"]): return jsonify(error="Turno inválido."), 400
        room.shift = str(data["shift"]).upper()
    if "lessonCount" in data:
        try: count = int(data["lessonCount"])
        except (TypeError, ValueError): return jsonify(error="Quantidade inválida."), 400
        if not 7 <= count <= 16: return jsonify(error="Use uma quantidade entre 7 e 16."), 400
        room.lesson_count = count
    db.session.commit()
    return jsonify(room=room.to_dict())


@api_bp.get("/rooms/<int:room_id>/schedules")
@jwt_required()
def list_schedules(room_id):
    room = find(Room, room_id)
    if not room: return jsonify(error="Sala não encontrada."), 404
    user = current_user()
    if user.role == "PROFESSOR" and room.shift != user.shift:
        return jsonify(error="Sala de outro turno."), 403
    try:
        start = date.fromisoformat(request.args.get("start", date.today().isoformat()))
        end = date.fromisoformat(request.args.get("end", start.isoformat()))
    except ValueError: return jsonify(error="Use datas no formato AAAA-MM-DD."), 400
    query = db.select(Schedule).join(User, Schedule.teacher_id == User.id).where(
        Schedule.room_id == room_id, Schedule.class_date.between(start, end))
    if user.role == "PROFESSOR": query = query.where(User.shift == user.shift)
    items = db.session.scalars(query.order_by(Schedule.class_date, Schedule.lesson_number)).all()
    return jsonify(room=room.to_dict(), items=[item.to_dict() for item in items])


@api_bp.post("/rooms/<int:room_id>/schedules")
@jwt_required()
def create_schedule(room_id):
    user = current_user()
    if user.role != "PROFESSOR": return jsonify(error="Somente professores podem agendar."), 403
    room = find(Room, room_id)
    if not room: return jsonify(error="Sala não encontrada."), 404
    if room.shift != user.shift: return jsonify(error="Você só pode agendar salas do seu turno."), 403
    data, missing = body_fields("date", "lessonNumber", "time")
    if missing: return jsonify(error="Data, aula e horário são obrigatórios."), 400
    try:
        class_date = date.fromisoformat(data["date"])
        lesson_number = int(data["lessonNumber"])
        class_time = time.fromisoformat(data["time"])
    except (ValueError, TypeError): return jsonify(error="Dados de agendamento inválidos."), 400
    if class_date < date.today() or not 1 <= lesson_number <= room.lesson_count:
        return jsonify(error="Data passada ou número de aula inválido."), 400
    item = Schedule(room_id=room_id, teacher_id=user.id, class_date=class_date,
                    lesson_number=lesson_number, class_time=class_time)
    db.session.add(item)
    try:
        db.session.flush()
        admins = db.session.scalars(db.select(User).where(User.role == "ADMIN", User.active.is_(True))).all()
        for admin in admins: notify(admin.id, "Nova aula agendada", f"{user.name} agendou {room.name} às {data['time']}.")
        db.session.commit()
    except IntegrityError:
        db.session.rollback(); return jsonify(error="Essa aula já está ocupada."), 409
    return jsonify(schedule=item.to_dict()), 201


@api_bp.patch("/schedules/<int:schedule_id>/status")
@admin_required
def update_schedule_status(schedule_id):
    item = find(Schedule, schedule_id)
    if not item: return jsonify(error="Agendamento não encontrado."), 404
    status = str((request.get_json(silent=True) or {}).get("status", "")).upper()
    if status not in SCHEDULE_STATUSES: return jsonify(error="Status inválido."), 400
    item.status = status
    if status == "CANCELADA":
        item.cancelled_by_id = int(get_jwt_identity()); item.cancelled_at = datetime.now(timezone.utc)
    notify(item.teacher_id, "Status da aula alterado", f"A aula em {item.room.name} agora está {status}.")
    db.session.commit()
    return jsonify(schedule=item.to_dict())


@api_bp.delete("/schedules/<int:schedule_id>")
@jwt_required()
def cancel_schedule(schedule_id):
    item = find(Schedule, schedule_id)
    if not item: return jsonify(error="Agendamento não encontrado."), 404
    user = current_user()
    if user.role != "ADMIN" and item.teacher_id != user.id:
        return jsonify(error="Você não pode cancelar esta aula."), 403
    item.status = "CANCELADA"; item.cancelled_by_id = user.id
    item.cancelled_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(schedule=item.to_dict())


@api_bp.get("/notifications")
@jwt_required()
def list_notifications():
    items = db.session.scalars(db.select(Notification).where(
        Notification.user_id == int(get_jwt_identity())).order_by(Notification.created_at.desc()).limit(50)).all()
    unread = db.session.scalar(db.select(func.count(Notification.id)).where(
        Notification.user_id == int(get_jwt_identity()), Notification.read.is_(False)))
    return jsonify(unreadCount=unread, items=[item.to_dict() for item in items])


@api_bp.patch("/notifications/<int:notification_id>/read")
@jwt_required()
def read_notification(notification_id):
    item = find(Notification, notification_id)
    if not item or item.user_id != int(get_jwt_identity()):
        return jsonify(error="Notificação não encontrada."), 404
    item.read = True; db.session.commit()
    return jsonify(notification=item.to_dict())

