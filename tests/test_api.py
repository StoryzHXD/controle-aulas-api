from datetime import date, timedelta
import pytest
from app import create_app
from app.extensions import db


@pytest.fixture()
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-with-at-least-32-bytes",
    })
    with app.app_context():
        db.create_all()
    with app.test_client() as test_client:
        yield test_client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_complete_permissions_flow(client):
    assert client.post("/api/auth/bootstrap", json={"name": "admin", "password": "admin123"}).status_code == 201
    assert client.post("/api/auth/bootstrap", json={"name": "x", "password": "12345678"}).status_code == 409

    admin_login = client.post("/api/auth/login", json={"name": "admin", "password": "admin123"}).get_json()
    admin_token = admin_login["accessToken"]
    teacher = client.post("/api/teachers", headers=auth(admin_token),
                          json={"name": "Hadrian", "password": "prof1234"})
    assert teacher.status_code == 201
    room = client.post("/api/rooms", headers=auth(admin_token),
                       json={"name": "Sala 1", "lessonCount": 6})
    room_id = room.get_json()["room"]["id"]

    teacher_login = client.post("/api/auth/login", json={"name": "Hadrian", "password": "prof1234"}).get_json()
    teacher_token = teacher_login["accessToken"]
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    scheduled = client.post(f"/api/rooms/{room_id}/schedules", headers=auth(teacher_token),
                            json={"date": tomorrow, "lessonNumber": 1})
    assert scheduled.status_code == 201
    assert client.post(f"/api/rooms/{room_id}/schedules", headers=auth(admin_token),
                       json={"date": tomorrow, "lessonNumber": 2}).status_code == 403
    schedule_id = scheduled.get_json()["schedule"]["id"]
    assert client.delete(f"/api/schedules/{schedule_id}", headers=auth(admin_token)).status_code == 204
