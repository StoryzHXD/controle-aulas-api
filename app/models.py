from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db

SHIFTS = ("MANHA", "TARDE", "NOITE")
SCHEDULE_STATUSES = ("AGENDADA", "CONFIRMADA", "CANCELADA")


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="PROFESSOR")
    subject = db.Column(db.String(100))
    shift = db.Column(db.String(10), index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email,
                "role": self.role, "subject": self.subject, "shift": self.shift,
                "active": self.active}


class Room(db.Model):
    __tablename__ = "rooms"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    shift = db.Column(db.String(10), nullable=False, index=True)
    lesson_count = db.Column(db.Integer, nullable=False, default=7)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "shift": self.shift,
                "lessonCount": self.lesson_count, "active": self.active}


class Schedule(db.Model):
    __tablename__ = "schedules"
    __table_args__ = (db.UniqueConstraint("room_id", "class_date", "lesson_number",
                                          name="uq_room_date_lesson"),)
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_date = db.Column(db.Date, nullable=False, index=True)
    lesson_number = db.Column(db.Integer, nullable=False)
    class_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="AGENDADA")
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancelled_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    room = db.relationship("Room")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])

    def to_dict(self):
        return {"id": self.id, "roomId": self.room_id, "roomName": self.room.name,
                "teacherId": self.teacher_id, "teacherName": self.teacher.name,
                "teacherShift": self.teacher.shift, "date": self.class_date.isoformat(),
                "lessonNumber": self.lesson_number,
                "time": self.class_time.strftime("%H:%M"), "status": self.status,
                "cancelledById": self.cancelled_by_id}


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "message": self.message,
                "read": self.read, "createdAt": self.created_at.isoformat()}

