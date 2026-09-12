from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="PROFESSOR")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "role": self.role,
                "active": self.active}


class Room(db.Model):
    __tablename__ = "rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    lesson_count = db.Column(db.Integer, nullable=False, default=6)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name,
                "lessonCount": self.lesson_count, "active": self.active}


class Schedule(db.Model):
    __tablename__ = "schedules"
    __table_args__ = (
        db.UniqueConstraint("room_id", "class_date", "lesson_number",
                            name="uq_room_date_lesson"),
    )

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_date = db.Column(db.Date, nullable=False, index=True)
    lesson_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    room = db.relationship("Room")
    teacher = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "roomId": self.room_id,
            "roomName": self.room.name,
            "teacherId": self.teacher_id,
            "teacherName": self.teacher.name,
            "date": self.class_date.isoformat(),
            "lessonNumber": self.lesson_number,
        }

