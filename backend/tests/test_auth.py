"""Exercise identity HTTP flows against an isolated real MongoDB database."""
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from fastapi import Depends
from jose import jwt

os.environ["MONGODB_DB"] = "etsip_test_" + uuid.uuid4().hex
os.environ["JWT_SECRET"] = "test-secret-with-more-than-thirty-two-characters"
os.environ["ADMIN_PASSWORD"] = "First-admin-password-123"
os.environ["DEMO_PASSWORD"] = "First-demo-password-123"
os.environ["SEED_ON_STARTUP"] = "true"

from app.main import app
from app.core.security import require_permission


@app.get('/test-permission')
async def guard_route(user: dict = Depends(require_permission('administer'))):
    """Expose a test-only endpoint for the shared permission dependency."""
    return {"role": user["role"]}


@pytest.fixture(scope="module")
def client():
    """Start the real application and remove only its unique test database."""
    with TestClient(app) as test_client:
        yield test_client
    mongo = MongoClient(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017"))
    mongo.drop_database(os.environ["MONGODB_DB"])
    mongo.close()


def login(client, email="engineer@ketsip.local", password="First-demo-password-123"):
    """Submit credentials through the public endpoint."""
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_seed_login_and_audit(client):
    """Verify all seeded roles, authentication, and password-free audit records."""
    db = MongoClient(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017"))[os.environ["MONGODB_DB"]]
    assert db.roles.count_documents({}) == 6
    assert db.users.count_documents({}) == 6
    assert login(client, password="wrong").status_code == 401
    assert login(client, email="nobody@ketsip.local").status_code == 401
    result = login(client)
    assert result.status_code == 200
    assert result.json()["user"]["role"] == "Engineer"
    assert "passwordHash" not in str(result.json())
    assert db.audit_logs.count_documents({"action": "login", "details": "Login failed"}) >= 2
    assert db.audit_logs.count_documents({"action": "login", "details": "Login succeeded"}) >= 1
    unknown = db.audit_logs.find_one({"userName": "Unknown user"})
    assert unknown["userId"] is None
    assert "wrong" not in str(list(db.audit_logs.find({})))


def test_protected_profile_preference_and_logout(client):
    """Enforce authentication, validate preference, persist, and revoke logout tokens."""
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    token = login(client).json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    assert client.get('/api/auth/me', headers=headers).json()['email'] == 'engineer@ketsip.local'
    assert client.put('/api/auth/profile', headers=headers, json={'defaultLandingPage': 'unsafe'}).status_code == 422
    assert client.put('/api/auth/profile', headers=headers, json={'role': 'Administrator', 'defaultLandingPage': 'dashboard'}).status_code == 422
    assert client.put('/api/auth/profile', headers=headers, json={'defaultLandingPage': 'dashboard'}).status_code == 200
    assert client.get('/api/auth/me', headers=headers).json()['defaultLandingPage'] == 'dashboard'
    assert client.post('/api/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/auth/me', headers=headers).status_code == 401


def test_admin_password_change_revokes_old_sessions(client):
    """Verify first-use flag, password validation, and token invalidation."""
    response = login(client, 'admin@ketsip.local', 'First-admin-password-123')
    assert response.json()['user']['mustChangePassword'] is True
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    assert client.get('/test-permission', headers=headers).status_code == 403
    assert client.get('/test-permission', headers={'Authorization': 'Bearer ' + login(client).json()['token']}).status_code == 403
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'wrong', 'newPassword': 'Replacement-password-456'}).status_code == 400
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'short'}).status_code == 422
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'Replacement-password-456'}).status_code == 204
    assert client.get('/api/auth/me', headers=headers).status_code == 401
    assert login(client, 'admin@ketsip.local', 'First-admin-password-123').status_code == 401
    updated = login(client, 'admin@ketsip.local', 'Replacement-password-456').json()
    assert updated['user']['mustChangePassword'] is False
    assert client.get('/test-permission', headers={'Authorization': 'Bearer ' + updated['token']}).status_code == 200


def test_expiry_and_password_boundary(client):
    """Reject missing token expiry and bcrypt-incompatible passwords."""
    user = login(client).json()['user']
    token = jwt.encode({'sub': user['id'], 'role': user['role'], 'ver': 0}, os.environ['JWT_SECRET'], algorithm='HS256')
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code == 401
    assert login(client, password='bad\x00password').status_code == 401
