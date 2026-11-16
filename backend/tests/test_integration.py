"""Verify inventory, access, insight and audit consistency across features."""
import os
import uuid
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient
from app.main import app


@pytest.fixture
def system(monkeypatch):
    """Start an isolated real Mongo database for a complete lifecycle."""
    name = 'etsip_integration_' + uuid.uuid4().hex
    monkeypatch.setenv('MONGODB_DB', name)
    monkeypatch.setenv('JWT_SECRET', 'integration-secret-at-least-thirty-two-characters')
    monkeypatch.setenv('ADMIN_PASSWORD', 'Initial-admin-password-123')
    monkeypatch.setenv('DEMO_PASSWORD', 'Initial-demo-password-123')
    monkeypatch.setenv('SEED_ON_STARTUP', 'true')
    mongo = MongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
    try:
        with TestClient(app) as client:
            response = client.post('/api/auth/login', json={'email': 'admin@ketsip.local', 'password': 'Initial-admin-password-123'})
            assert response.status_code == 200
            auth = {'Authorization': 'Bearer ' + response.json()['token']}
            changed = client.put('/api/auth/password', headers=auth, json={'currentPassword': 'Initial-admin-password-123', 'newPassword': 'Changed-admin-password-456'})
            assert changed.status_code == 204
            response = client.post('/api/auth/login', json={'email': 'admin@ketsip.local', 'password': 'Changed-admin-password-456'})
            assert response.status_code == 200
            yield client, mongo[name], {'Authorization': 'Bearer ' + response.json()['token']}
    finally:
        mongo.drop_database(name)
        mongo.close()


def portfolio(client, auth, name):
    """Create a portfolio using the actual inventory endpoint."""
    response = client.post('/api/portfolios', headers=auth, json={'name': name, 'owner': 'Demo Owner', 'description': '', 'productArea': 'Integration', 'status': 'Active'})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_inventory_lifecycle_updates_all_read_models_and_audit(system):
    """Chain auth, portfolios, applications, dashboard, reports and audit."""
    client, db, auth = system
    first = portfolio(client, auth, 'Integration First')
    second = portfolio(client, auth, 'Integration Second')
    payload = {'name': 'Integration App', 'portfolioId': first, 'qualityScore': 88, 'applicationHealthScore': 76, 'automationCoverage': 64, 'openCriticalDefects': 3, 'riskLevel': 'High', 'productArea': 'Integration'}
    created = client.post('/api/applications', headers=auth, json=payload)
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    blocked = client.delete('/api/portfolios/' + first, headers=auth)
    assert blocked.status_code == 409
    assert db.applications.find_one({'_id': ObjectId(identifier)})['portfolioId'] == first
    for endpoint in ['/api/portfolios/' + first, '/api/dashboard/executive?portfolioId=' + first]:
        response = client.get(endpoint, headers=auth)
        assert response.status_code == 200
        assert response.json().get('qualityScore', response.json().get('enterpriseQualityScore')) == 88
    report = client.get('/api/reports/applications', headers=auth, params={'portfolioId': first})
    assert report.status_code == 200
    assert report.json()['items'][0]['id'] == identifier
    exported = client.get('/api/reports/applications', headers=auth, params={'portfolioId': first, 'format': 'csv'})
    assert exported.status_code == 200
    assert 'Integration App' in exported.text
    updated = client.put('/api/applications/' + identifier, headers=auth, json={**payload, 'portfolioId': second, 'qualityScore': 42})
    assert updated.status_code == 200
    old = client.get('/api/portfolios/' + first, headers=auth)
    assert old.status_code == 200 and old.json()['applicationCount'] == 0
    new = client.get('/api/dashboard/executive', headers=auth, params={'portfolioId': second})
    assert new.status_code == 200 and new.json()['enterpriseQualityScore'] == 42
    report = client.get('/api/reports/portfolios', headers=auth, params={'search': 'Integration Second'})
    assert report.status_code == 200 and report.json()['items'][0]['qualityScore'] == 42
    assert client.delete('/api/applications/' + identifier, headers=auth).status_code == 204
    assert client.delete('/api/portfolios/' + first, headers=auth).status_code == 204
    assert client.delete('/api/portfolios/' + second, headers=auth).status_code == 204
    assert db.applications.count_documents({'portfolioId': {'$in': [first, second]}}) == 0
    events = list(db.audit_logs.find({'entityId': identifier}))
    assert {event['action'] for event in events} == {'create', 'edit', 'delete'}
    assert db.audit_logs.count_documents({'action': 'export'}) >= 1


def test_missing_and_scoped_dependencies_do_not_create_orphans(system):
    """Reject missing and foreign scope references without downstream changes."""
    client, db, admin = system
    foreign = portfolio(client, admin, 'Foreign Integration')
    login = client.post('/api/auth/login', json={'email': 'leader@ketsip.local', 'password': 'Initial-demo-password-123'})
    assert login.status_code == 200
    leader = {'Authorization': 'Bearer ' + login.json()['token']}
    before = db.applications.count_documents({})
    audit_before = db.audit_logs.count_documents({'entityType': 'application'})
    rejected = client.post('/api/applications', headers=leader, json={'name': 'Forbidden Integration', 'portfolioId': foreign})
    assert rejected.status_code == 403
    missing = client.post('/api/applications', headers=admin, json={'name': 'Missing Integration', 'portfolioId': str(ObjectId())})
    assert missing.status_code == 422
    assert db.audit_logs.count_documents({'entityType': 'application'}) == audit_before
    assert db.applications.count_documents({}) == before
    report = client.get('/api/reports/applications', headers=leader, params={'portfolioId': foreign})
    assert report.status_code == 200 and report.json()['total'] == 0
    dashboard = client.get('/api/dashboard/executive', headers=leader, params={'portfolioId': foreign})
    assert dashboard.status_code == 200 and dashboard.json()['totalApplications'] == 0


def test_admin_assignments_drive_scope_and_permission_consumers(system):
    """Propagate managed access changes into inventory, insights and exports."""
    client, db, admin = system
    assigned = portfolio(client, admin, 'Assigned Integration')
    created = client.post('/api/applications', headers=admin, json={'name': 'Assigned App', 'portfolioId': assigned})
    assert created.status_code == 201
    user = db.users.find_one({'role': 'Portfolio Leader'})
    identifier = str(user['_id'])
    payload = {key: user[key] for key in ['name', 'email', 'role', 'status', 'portfolioAccess']}
    updated = client.put('/api/users/' + identifier, headers=admin, json={**payload, 'portfolioAccess': [assigned]})
    assert updated.status_code == 200
    login = client.post('/api/auth/login', json={'email': user['email'], 'password': 'Initial-demo-password-123'})
    assert login.status_code == 200
    leader = {'Authorization': 'Bearer ' + login.json()['token']}
    for path in ['/api/applications', '/api/reports/applications']:
        response = client.get(path, headers=leader)
        assert response.status_code == 200 and response.json()['total'] == 1
    response = client.get('/api/dashboard/executive', headers=leader)
    assert response.status_code == 200 and response.json()['totalApplications'] == 1
    role = db.roles.find_one({'name': 'Portfolio Leader'})
    changed = client.put('/api/roles/' + str(role['_id']), headers=admin, json={'name': role['name'], 'description': role['description'], 'permissions': ['view']})
    assert changed.status_code == 200
    denied = client.get('/api/reports/applications?format=csv', headers=leader)
    assert denied.status_code == 403
    updated = client.put('/api/users/' + identifier, headers=admin, json={**payload, 'portfolioAccess': []})
    assert updated.status_code == 200
    response = client.get('/api/reports/applications', headers=leader)
    assert response.status_code == 200 and response.json()['total'] == 0
    assert db.audit_logs.count_documents({'action': 'permissionChange', 'entityType': 'role'}) == 1
    assert db.users.find_one({'_id': user['_id']})['portfolioAccess'] == []
