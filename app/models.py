from datetime import datetime, timezone

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from .extensions import db


SHIFTS = ("MANHA", "TARDE", "NOITE")

SCHEDULE_STATUSES = (
    "AGENDADA",
    "CONFIRMADA",
    "CANCELADA",
)


def utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    father_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="PROFESSOR",
        index=True,
    )

    subject = db.Column(
        db.String(100),
        nullable=True,
    )

    shift = db.Column(
        db.String(10),
        nullable=True,
        index=True,
    )

    active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    email_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    verification_code_hash = db.Column(
        db.String(255),
        nullable=True,
    )

    verification_expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    verification_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    verification_last_sent_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    father = db.relationship(
        "User",
        remote_side=[id],
        foreign_keys=[father_id],
        back_populates="children",
    )

    children = db.relationship(
        "User",
        foreign_keys=[father_id],
        back_populates="father",
        cascade="all, delete-orphan",
        single_parent=True,
        lazy=True,
    )

    taught_schedules = db.relationship(
        "Schedule",
        foreign_keys="Schedule.teacher_id",
        back_populates="teacher",
        lazy=True,
    )

    cancelled_schedules = db.relationship(
        "Schedule",
        foreign_keys="Schedule.cancelled_by_id",
        back_populates="cancelled_by",
        lazy=True,
    )

    notifications = db.relationship(
        "Notification",
        foreign_keys="Notification.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy=True,
    )
    

    def set_password(self, password):
        self.password_hash = generate_password_hash(
            str(password)
        )

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            str(password),
        )

    def owner_id(self):
        if self.role == "ADMIN":
            return self.id

        return self.father_id

    def to_dict(self):
        return {
            "id": self.id,
            "fatherId": self.father_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "subject": self.subject,
            "shift": self.shift,
            "active": self.active,
            "emailVerified": self.email_verified,
            "createdAt": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }


class Room(db.Model):
    __tablename__ = "rooms"

    __table_args__ = (
        db.UniqueConstraint(
            "father_id",
            "name",
            name="uq_rooms_father_name",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    father_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name = db.Column(
        db.String(100),
        nullable=False,
    )

    shift = db.Column(
        db.String(10),
        nullable=False,
        index=True,
    )

    lesson_count = db.Column(
        db.Integer,
        nullable=False,
        default=7,
    )

    active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    owner = db.relationship(
        "User",
        foreign_keys=[father_id],
    )

    schedules = db.relationship(
        "Schedule",
        back_populates="room",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "fatherId": self.father_id,
            "name": self.name,
            "shift": self.shift,
            "lessonCount": self.lesson_count,
            "active": self.active,
            "createdAt": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }


class Schedule(db.Model):
    __tablename__ = "schedules"

    __table_args__ = (
        db.UniqueConstraint(
            "father_id",
            "room_id",
            "class_date",
            "lesson_number",
            name="uq_schedules_father_room_date_lesson",
        ),
    )

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    father_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    room_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "rooms.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    class_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    lesson_number = db.Column(
        db.Integer,
        nullable=False,
    )

    class_time = db.Column(
        db.Time,
        nullable=False,
    )

    status = db.Column(
        db.String(20),
        nullable=False,
        default="AGENDADA",
        index=True,
    )

    cancelled_by_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    cancelled_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    owner = db.relationship(
        "User",
        foreign_keys=[father_id],
    )

    room = db.relationship(
        "Room",
        back_populates="schedules",
    )

    teacher = db.relationship(
        "User",
        foreign_keys=[teacher_id],
        back_populates="taught_schedules",
    )

    cancelled_by = db.relationship(
        "User",
        foreign_keys=[cancelled_by_id],
        back_populates="cancelled_schedules",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "fatherId": self.father_id,
            "roomId": self.room_id,
            "roomName": (
                self.room.name
                if self.room
                else None
            ),
            "teacherId": self.teacher_id,
            "teacherName": (
                self.teacher.name
                if self.teacher
                else None
            ),
            "teacherShift": (
                self.teacher.shift
                if self.teacher
                else None
            ),
            "date": (
                self.class_date.isoformat()
                if self.class_date
                else None
            ),
            "lessonNumber": self.lesson_number,
            "time": (
                self.class_time.strftime("%H:%M")
                if self.class_time
                else None
            ),
            "status": self.status,
            "cancelledById": self.cancelled_by_id,
            "cancelledAt": (
                self.cancelled_at.isoformat()
                if self.cancelled_at
                else None
            ),
            "createdAt": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }

class Occurrence(db.Model):
    __tablename__ = "occurrences"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    # Administrador/escola responsável pelos dados.
    father_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # Professor que registrou a ocorrência.
    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    student_name = db.Column(
        db.String(150),
        nullable=False,
    )

    # String para preservar zeros à esquerda.
    student_ra = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    reason = db.Column(
        db.Text,
        nullable=False,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    owner = db.relationship(
        "User",
        foreign_keys=[father_id],
    )

    teacher = db.relationship(
        "User",
        foreign_keys=[teacher_id],
    )

    def to_dict(self):
        return {
            "id": self.id,
            "fatherId": self.father_id,
            "teacherId": self.teacher_id,
            "teacherName": (
                self.teacher.name
                if self.teacher
                else None
            ),
            "studentName": self.student_name,
            "studentRa": self.student_ra,
            "reason": self.reason,
            "createdAt": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }
    
class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    father_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    title = db.Column(
        db.String(150),
        nullable=False,
    )

    message = db.Column(
        db.String(500),
        nullable=False,
    )

    read = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    owner = db.relationship(
        "User",
        foreign_keys=[father_id],
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="notifications",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "fatherId": self.father_id,
            "userId": self.user_id,
            "title": self.title,
            "message": self.message,
            "read": self.read,
            "createdAt": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),
        }