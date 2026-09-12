from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError
from .auth import admin_required, body_fields
from .extensions import db
from .models import Room, Schedule, User

api_bp = Blueprint("api", __name__, url_prefix="/api")


def get_or_404(model, item_id, label):
    item = db.session.get(model, item_id)
    return item, None if item else (jsonify(error=f"{label} não encontrado(a)."), 404)


@api_bp.get("/health")
def health():
    return jsonify(status="ok")


@api_bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or not user.active:
        return jsonify(error="Usuário inativo ou inexistente."), 401
    return jsonify(user=user.to_dict())


@api_bp.get("/teachers")
@admin_required
def list_teachers():
    teachers = db.session.scalars(
        db.select(User).where(User.role == "PROFESSOR").order_by(User.name)
    ).all()
    return jsonify(items=[teacher.to_dict() for teacher in teachers])


@api_bp.post("/teachers")
@admin_required
def create_teacher():
    data, missing = body_fields("name", "password")
    if missing:
        return jsonify(error="Nome e senha são obrigatórios."), 400
    if len(data["password"]) < 8:
        return jsonify(error="A senha deve possuir pelo menos 8 caracteres."), 400
    teacher = User(name=data["name"].strip(), role="PROFESSOR")
    teacher.set_password(data["password"])
    db.session.add(teacher)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Nome de usuário já utilizado."), 409
    return jsonify(teacher=teacher.to_dict()), 201


@api_bp.patch("/teachers/<int:teacher_id>")
@admin_required
def update_teacher(teacher_id):
    teacher, error = get_or_404(User, teacher_id, "Professor")
    if error:
        return error
    if teacher.role != "PROFESSOR":
        return jsonify(error="O usuário informado não é professor."), 400
    data = request.get_json(silent=True) or {}
    if "name" in data and str(data["name"]).strip():
        teacher.name = str(data["name"]).strip()
    if "password" in data:
        if len(str(data["password"])) < 8:
            return jsonify(error="A senha deve possuir pelo menos 8 caracteres."), 400
        teacher.set_password(str(data["password"]))
    if "active" in data:
        teacher.active = bool(data["active"])
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Nome de usuário já utilizado."), 409
    return jsonify(teacher=teacher.to_dict())


@api_bp.get("/rooms")
@jwt_required()
def list_rooms():
    rooms = db.session.scalars(db.select(Room).where(Room.active.is_(True)).order_by(Room.name)).all()
    return jsonify(items=[room.to_dict() for room in rooms])


@api_bp.post("/rooms")
@admin_required
def create_room():
    data, missing = body_fields("name")
    if missing:
        return jsonify(error="O nome da sala é obrigatório."), 400
    count = data.get("lessonCount", 6)
    if not isinstance(count, int) or not 1 <= count <= 20:
        return jsonify(error="lessonCount deve ser um inteiro entre 1 e 20."), 400
    room = Room(name=data["name"].strip(), lesson_count=count)
    db.session.add(room)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Já existe uma sala com esse nome."), 409
    return jsonify(room=room.to_dict()), 201


@api_bp.patch("/rooms/<int:room_id>")
@admin_required
def update_room(room_id):
    room, error = get_or_404(Room, room_id, "Sala")
    if error:
        return error
    data = request.get_json(silent=True) or {}
    if "name" in data and str(data["name"]).strip():
        room.name = str(data["name"]).strip()
    if "lessonCount" in data:
        count = data["lessonCount"]
        if not isinstance(count, int) or not 1 <= count <= 20:
            return jsonify(error="lessonCount deve ser um inteiro entre 1 e 20."), 400
        room.lesson_count = count
    if "active" in data:
        room.active = bool(data["active"])
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Já existe uma sala com esse nome."), 409
    return jsonify(room=room.to_dict())


@api_bp.get("/rooms/<int:room_id>/schedules")
@jwt_required()
def list_schedules(room_id):
    room, error = get_or_404(Room, room_id, "Sala")
    if error:
        return error
    start_raw = request.args.get("start")
    end_raw = request.args.get("end")
    try:
        start = date.fromisoformat(start_raw) if start_raw else date.today()
        end = date.fromisoformat(end_raw) if end_raw else start
    except ValueError:
        return jsonify(error="Use datas no formato AAAA-MM-DD."), 400
    if end < start or (end - start).days > 31:
        return jsonify(error="O período deve possuir entre 1 e 32 dias."), 400
    items = db.session.scalars(
        db.select(Schedule).where(Schedule.room_id == room.id,
                                  Schedule.class_date.between(start, end))
        .order_by(Schedule.class_date, Schedule.lesson_number)
    ).all()
    return jsonify(room=room.to_dict(), items=[item.to_dict() for item in items])


@api_bp.post("/rooms/<int:room_id>/schedules")
@jwt_required()
def create_schedule(room_id):
    if get_jwt().get("role") != "PROFESSOR":
        return jsonify(error="Somente professores podem agendar aulas."), 403
    room, error = get_or_404(Room, room_id, "Sala")
    if error:
        return error
    data, missing = body_fields("date", "lessonNumber")
    if missing:
        return jsonify(error="Data e número da aula são obrigatórios."), 400
    try:
        class_date = date.fromisoformat(data["date"])
        lesson_number = int(data["lessonNumber"])
    except (ValueError, TypeError):
        return jsonify(error="Data ou número da aula inválido."), 400
    if class_date < date.today():
        return jsonify(error="Não é possível agendar uma data passada."), 400
    if not 1 <= lesson_number <= room.lesson_count:
        return jsonify(error="Número de aula fora do limite da sala."), 400
    schedule = Schedule(room_id=room.id, teacher_id=int(get_jwt_identity()),
                        class_date=class_date, lesson_number=lesson_number)
    db.session.add(schedule)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="Essa aula já está ocupada nessa sala e data."), 409
    return jsonify(schedule=schedule.to_dict()), 201


@api_bp.delete("/schedules/<int:schedule_id>")
@jwt_required()
def delete_schedule(schedule_id):
    schedule, error = get_or_404(Schedule, schedule_id, "Agendamento")
    if error:
        return error
    role = get_jwt().get("role")
    user_id = int(get_jwt_identity())
    if role != "ADMIN" and schedule.teacher_id != user_id:
        return jsonify(error="Você não pode remover este agendamento."), 403
    db.session.delete(schedule)
    db.session.commit()
    return "", 204

