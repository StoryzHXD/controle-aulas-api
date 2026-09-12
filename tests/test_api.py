from datetime import date, timedelta
import pytest
from app import create_app
from app.extensions import db


@pytest.fixture()
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "JWT_SECRET_KEY": "test-secret-with-at-least-32-bytes"})
    with app.app_context(): db.create_all()
    with app.test_client() as value: yield value


def bearer(token): return {"Authorization": f"Bearer {token}"}
def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password}).get_json()["accessToken"]


def test_v2_flow(client):
    response = client.post("/api/auth/bootstrap", json={"name": "Admin", "email": "admin@escola.com", "password": "admin1234"})
    assert response.status_code == 201
    admin = login(client, "admin@escola.com", "admin1234")
    teacher = client.post("/api/teachers", headers=bearer(admin), json={
        "name": "Ana", "email": "ana@escola.com", "password": "prof1234",
        "subject": "Matemática", "shift": "MANHA"})
    assert teacher.status_code == 201
    room = client.post("/api/rooms", headers=bearer(admin), json={
        "name": "Sala 101", "shift": "MANHA", "lessonCount": 10})
    assert room.status_code == 201
    teacher_token = login(client, "ana@escola.com", "prof1234")
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    scheduled = client.post("/api/rooms/1/schedules", headers=bearer(teacher_token),
                            json={"date": tomorrow, "lessonNumber": 1, "time": "07:00"})
    assert scheduled.status_code == 201
    schedule_id = scheduled.get_json()["schedule"]["id"]
    assert client.patch(f"/api/schedules/{schedule_id}/status", headers=bearer(admin),
                        json={"status": "CONFIRMADA"}).status_code == 200
    assert client.delete(f"/api/schedules/{schedule_id}", headers=bearer(teacher_token)).get_json()["schedule"]["status"] == "CANCELADA"
    assert client.get("/api/notifications", headers=bearer(admin)).status_code == 200
