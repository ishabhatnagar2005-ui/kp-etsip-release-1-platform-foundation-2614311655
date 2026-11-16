"""Exercise identity HTTP flows against an isolated real MongoDB database."""
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from fastapi import Depends
from jose import jwt

from app.main import app
from app.core.security import require_permission


@app.get('/test-permission')
async def guard_route(user: dict = Depends(require_permission('administer'))):
    """Expose a test-only endpoint for the shared permission dependency."""
    return {"role": user["role"]}


@pytest.fixture(scope="module")
def client():
    """Start the real application and remove only its unique test database."""
    name = "etsip_test_" + uuid.uuid4().hex
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MONGODB_DB", name)
        env.setenv("JWT_SECRET", "test-secret-with-more-than-thirty-two-characters")
        env.setenv("ADMIN_PASSWORD", "First-admin-password-123")
        env.setenv("DEMO_PASSWORD", "First-demo-password-123")
        env.setenv("SEED_ON_STARTUP", "true")
        mongo = MongoClient(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017"))
        try:
            with TestClient(app) as test_client:
                yield test_client
        finally:
            mongo.drop_database(name)
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
    response = login(client)
    assert response.status_code == 200
    token = response.json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    response = client.get('/api/auth/me', headers=headers)
    assert response.status_code == 200
    assert response.json()['email'] == 'engineer@ketsip.local'
    assert client.put('/api/auth/profile', headers=headers, json={'defaultLandingPage': 'unsafe'}).status_code == 422
    assert client.put('/api/auth/profile', headers=headers, json={'role': 'Administrator', 'defaultLandingPage': 'dashboard'}).status_code == 422
    assert client.put('/api/auth/profile', headers=headers, json={'defaultLandingPage': 'dashboard'}).status_code == 200
    response = client.get('/api/auth/me', headers=headers)
    assert response.status_code == 200
    assert response.json()['defaultLandingPage'] == 'dashboard'
    assert client.post('/api/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/auth/me', headers=headers).status_code == 401


def test_admin_password_change_revokes_old_sessions(client):
    """Verify first-use flag, password validation, and token invalidation."""
    response = login(client, 'admin@ketsip.local', 'First-admin-password-123')
    assert response.status_code == 200
    assert response.json()['user']['mustChangePassword'] is True
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    assert client.get('/test-permission', headers=headers).status_code == 403
    engineer = login(client)
    assert engineer.status_code == 200
    assert client.get('/test-permission', headers={'Authorization': 'Bearer ' + engineer.json()['token']}).status_code == 403
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'wrong', 'newPassword': 'Replacement-password-456'}).status_code == 400
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'short'}).status_code == 422
    assert client.put('/api/auth/password', headers=headers, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'Replacement-password-456'}).status_code == 204
    assert client.get('/api/auth/me', headers=headers).status_code == 401
    assert login(client, 'admin@ketsip.local', 'First-admin-password-123').status_code == 401
    response = login(client, 'admin@ketsip.local', 'Replacement-password-456')
    assert response.status_code == 200
    updated = response.json()
    assert updated['user']['mustChangePassword'] is False
    assert client.get('/test-permission', headers={'Authorization': 'Bearer ' + updated['token']}).status_code == 200


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}], ids=["missing", "invalid"])
@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/auth/logout", None),
    ("PUT", "/api/auth/password", {"currentPassword": "First-demo-password-123", "newPassword": "Replacement-password-456"}),
    ("PUT", "/api/auth/profile", {"defaultLandingPage": "applications"}),
])
def test_identity_mutations_reject_missing_or_invalid_token(client, headers, method, path, body):
    """Reject unauthenticated mutation requests even when their payload is valid."""
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 401


def test_expired_signed_token_is_rejected(client):
    """Reject a correctly signed token after its expiry time."""
    response = login(client)
    assert response.status_code == 200
    token = response.json()['token']
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code == 200
    claims = jwt.decode(token, os.environ['JWT_SECRET'], algorithms=['HS256'])
    claims['exp'] = datetime.now(timezone.utc) - timedelta(minutes=5)
    expired = jwt.encode(claims, os.environ['JWT_SECRET'], algorithm='HS256')
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + expired}).status_code == 401


@pytest.mark.parametrize('field,new_value', [
    ('status', 'Inactive'),
    ('role', 'Auditor'),
    ('tokenVersion', None),
], ids=['inactive', 'stale-role', 'stale-version'])
def test_token_rejected_after_persisted_account_change(client, field, new_value):
    """Recheck account status, role, and token version from MongoDB on each request."""
    response = login(client)
    assert response.status_code == 200
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    assert client.get('/api/auth/me', headers=headers).status_code == 200
    with MongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')) as mongo:
        users = mongo[os.environ['MONGODB_DB']].users
        user = users.find_one({'email': 'engineer@ketsip.local'})
        assert user is not None
        original = user[field]
        replacement = original + 1 if field == 'tokenVersion' else new_value
        try:
            result = users.update_one({'_id': user['_id']}, {'$set': {field: replacement}})
            assert result.modified_count == 1
            assert users.find_one({'_id': user['_id']})[field] == replacement
            assert client.get('/api/auth/me', headers=headers).status_code == 401
        finally:
            users.update_one({'_id': user['_id']}, {'$set': {field: original}})
        assert client.get('/api/auth/me', headers=headers).status_code == 200


def test_expiry_and_password_boundary(client):
    """Reject missing token expiry and bcrypt-incompatible passwords."""
    response = login(client)
    assert response.status_code == 200
    user = response.json()['user']
    token = jwt.encode({'sub': user['id'], 'role': user['role'], 'ver': 0}, os.environ['JWT_SECRET'], algorithm='HS256')
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code == 401
    assert login(client, password='bad\x00password').status_code == 401


@pytest.mark.parametrize('field,invalid', [
    ('email', None), ('email', 123), ('email', 'e' * 255),
    ('password', None), ('password', {'$ne': ''}), ('password', 'p' * 1025),
    ('email', ...), ('password', ...),
], ids=['email-null', 'email-type', 'email-oversize', 'password-null',
        'password-type', 'password-oversize', 'email-missing', 'password-missing'])
def test_invalid_login_credentials_are_rejected_without_writes(client, field, invalid):
    """Reject malformed credentials before users or audit records are changed."""
    payload = {'email': 'engineer@ketsip.local', 'password': 'First-demo-password-123'}
    if invalid is ...:
        del payload[field]
    else:
        payload[field] = invalid
    with MongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')) as mongo:
        db = mongo[os.environ['MONGODB_DB']]
        before_users = list(db.users.find().sort('_id'))
        before_audit = list(db.audit_logs.find().sort('_id'))
        response = client.post('/api/auth/login', json=payload)
        assert response.status_code == 422
        assert list(db.users.find().sort('_id')) == before_users
        assert list(db.audit_logs.find().sort('_id')) == before_audit


@pytest.mark.parametrize('field,invalid', [
    ('currentPassword', None), ('currentPassword', 12), ('currentPassword', 'x' * 1025),
    ('newPassword', None), ('newPassword', ['wrong']), ('newPassword', 'x' * 73),
    ('currentPassword', ...), ('newPassword', ...),
], ids=['current-null', 'current-type', 'current-oversize', 'new-null',
        'new-type', 'new-oversize', 'current-missing', 'new-missing'])
def test_invalid_password_change_does_not_mutate_account(client, field, invalid):
    """Reject malformed password changes without changing persisted account or audit."""
    response = login(client)
    assert response.status_code == 200
    headers = {'Authorization': 'Bearer ' + response.json()['token']}
    payload = {'currentPassword': 'First-demo-password-123', 'newPassword': 'Replacement-password-456'}
    if invalid is ...:
        del payload[field]
    else:
        payload[field] = invalid
    with MongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')) as mongo:
        db = mongo[os.environ['MONGODB_DB']]
        before_users = list(db.users.find().sort('_id'))
        before_audit = list(db.audit_logs.find().sort('_id'))
        response = client.put('/api/auth/password', headers=headers, json=payload)
        assert response.status_code == 422
        assert list(db.users.find().sort('_id')) == before_users
        assert list(db.audit_logs.find().sort('_id')) == before_audit
