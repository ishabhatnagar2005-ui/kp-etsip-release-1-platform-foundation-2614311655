"""Exercise application services and HTTP endpoints against real MongoDB."""
import asyncio
import os
import uuid
import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient
from app.main import app
from app.applications.repository import ApplicationRepository
from app.applications.schema import ApplicationInput
from app.applications.service import create_application, delete_application, edit_application, list_applications, visible

URI = os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')
BODY = {'name': 'Inventory Test', 'description': 'Quality inventory', 'productArea': 'Payments', 'businessOwner': 'Business', 'technologyOwner': 'Tech', 'etsOwner': 'ETS', 'criticality': 'High', 'tier': 2, 'lifecycleStatus': 'Active', 'technologyStack': 'Python', 'repositoryLink': 'https://example.com/repo', 'pipelineLink': 'https://example.com/build', 'applicationHealthScore': 80, 'qualityScore': 90, 'automationCoverage': 60, 'unitTestCoverage': 75, 'openDefects': 8, 'openCriticalDefects': 2, 'riskLevel': 'High'}


@pytest.fixture
def context(monkeypatch):
    """Start a disposable seeded database and application."""
    name = 'etsip_applications_' + uuid.uuid4().hex
    monkeypatch.setenv('MONGODB_DB', name)
    monkeypatch.setenv('JWT_SECRET', 'test-secret-with-more-than-thirty-two-characters')
    monkeypatch.setenv('ADMIN_PASSWORD', 'First-admin-password-123')
    monkeypatch.setenv('DEMO_PASSWORD', 'First-demo-password-123')
    monkeypatch.setenv('SEED_ON_STARTUP', 'true')
    mongo = MongoClient(URI)
    try:
        with TestClient(app) as client:
            yield client, mongo[name]
    finally:
        mongo.drop_database(name)
        mongo.close()


def headers(client, role, password='First-demo-password-123'):
    """Authenticate one seeded user."""
    response = client.post('/api/auth/login', json={'email': role + '@ketsip.local', 'password': password})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def admin_headers(client):
    """Complete first-use administrator password setup."""
    token = headers(client, 'admin', 'First-admin-password-123')
    assert client.put('/api/auth/password', headers=token, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'Replacement-password-456'}).status_code == 204
    return headers(client, 'admin', 'Replacement-password-456')


def test_crud_filters_persistence_and_audit(context):
    """Create, filter, retrieve, update and delete a persisted record."""
    client, db = context
    assert client.get('/api/applications').status_code == 401
    admin = admin_headers(client)
    assert db.applications.count_documents({}) == 10
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    payload = {**BODY, 'portfolioId': portfolio}
    created = client.post('/api/applications', headers=admin, json=payload)
    assert created.status_code == 201, created.text
    item = created.json()
    identifier = item['id']
    assert db.applications.find_one({'_id': ObjectId(identifier)})['businessOwner'] == 'Business'
    assert client.post('/api/applications', headers=admin, json=payload).status_code == 409
    detail = client.get(f'/api/applications/{identifier}', headers=admin)
    assert detail.status_code == 200
    assert detail.json()['qualityScore'] == 90
    result = client.get('/api/applications', headers=admin, params={'search': 'inventory test', 'portfolioId': portfolio, 'criticality': 'High', 'riskLevel': 'High', 'lifecycleStatus': 'Active'})
    assert result.status_code == 200
    assert result.json()['total'] == 1
    for key, value in [('portfolioId', str(ObjectId())), ('criticality', 'Low'), ('riskLevel', 'Low'), ('lifecycleStatus', 'Retired')]:
        result = client.get('/api/applications', headers=admin, params={'search': 'Inventory Test', key: value})
        assert result.status_code == 200
        assert result.json()['total'] == 0
    result = client.get('/api/applications', headers=admin, params={'search': '.*'})
    assert result.status_code == 200
    assert result.json()['total'] == 0
    result = client.get('/api/applications', headers=admin, params={'limit': 1, 'offset': 1})
    assert result.status_code == 200
    assert result.json()['total'] == 11
    updated = client.put(f'/api/applications/{identifier}', headers=admin, json={**payload, 'qualityScore': 42})
    assert updated.status_code == 200
    assert updated.json()['qualityScore'] == 42
    detail = client.get(f'/api/applications/{identifier}', headers=admin)
    assert detail.status_code == 200
    assert detail.json()['qualityScore'] == 42
    assert client.delete(f'/api/applications/{identifier}', headers=admin).status_code == 204
    assert client.get(f'/api/applications/{identifier}', headers=admin).status_code == 404
    assert client.put(f'/api/applications/{identifier}', headers=admin, json=payload).status_code == 404
    assert client.delete(f'/api/applications/{identifier}', headers=admin).status_code == 404
    assert [event['action'] for event in db.audit_logs.find({'entityType': 'application', 'entityId': identifier})] == ['create', 'edit', 'delete']


def test_validation_and_security_boundaries(context):
    """Reject invalid fields, unsafe input and unauthorized operations."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    payload = {**BODY, 'portfolioId': portfolio}
    for patch in [{'name': ' '}, {'name': {'$ne': ''}}, {'portfolioId': str(ObjectId())}, {'portfolioId': 'invalid'}, {'tier': 0}, {'tier': True}, {'tier': 5}, {'qualityScore': 101}, {'automationCoverage': -1}, {'openDefects': -1}, {'openCriticalDefects': 1.5}, {'criticality': 'Urgent'}, {'riskLevel': 'Critical'}, {'lifecycleStatus': 'Unknown'}, {'repositoryLink': 'javascript:alert(1)'}, {'pipelineLink': 'https://user:pass@example.com'}, {'extra': 'injected'}]:
        response = client.post('/api/applications', headers=admin, json={**payload, **patch})
        assert response.status_code == 422, (patch, response.text)
    for params in [{'limit': 101}, {'offset': -1}, {'criticality': 'No'}, {'riskLevel': 'No'}, {'lifecycleStatus': 'No'}]:
        assert client.get('/api/applications', headers=admin, params=params).status_code == 422
    assert client.get('/api/applications/not-id', headers=admin).status_code == 404
    assert client.put('/api/applications/not-id', headers=admin, json=payload).status_code == 404
    assert client.delete('/api/applications/not-id', headers=admin).status_code == 404
    existing = str(db.applications.find_one({'name': 'Payment Gateway'})['_id'])
    assert client.put(f'/api/applications/{existing}', headers=admin, json={**payload, 'name': 'Billing Ledger'}).status_code == 409
    for role in ['executive', 'auditor', 'readonly']:
        token = headers(client, role)
        assert client.get('/api/applications', headers=token).status_code == 200
        assert client.post('/api/applications', headers=token, json=payload).status_code == 403
        assert client.put(f'/api/applications/{existing}', headers=token, json=payload).status_code == 403
        assert client.delete(f'/api/applications/{existing}', headers=token).status_code == 403
    engineer = headers(client, 'engineer')
    assert client.post('/api/applications', headers=engineer, json=payload).status_code == 201
    assert client.delete(f'/api/applications/{existing}', headers=engineer).status_code == 403
    db.roles.update_one({'name': 'Engineer'}, {'$pull': {'permissions': 'edit'}})
    assert client.put(f'/api/applications/{existing}', headers=engineer, json=payload).status_code == 403


def test_leader_scope_including_reassignment(context):
    """Constrain existing records, destination portfolio and empty assignments."""
    client, db = context
    leader = headers(client, 'leader')
    assigned = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    other = str(db.portfolios.find_one({'name': 'Customer Platform'})['_id'])
    other_app = str(db.applications.find_one({'portfolioId': other})['_id'])
    own_app = str(db.applications.find_one({'portfolioId': assigned})['_id'])
    result = client.get('/api/applications', headers=leader)
    assert result.status_code == 200
    assert result.json()['total'] == 4
    result = client.get('/api/applications', headers=leader, params={'portfolioId': other})
    assert result.status_code == 200
    assert result.json()['total'] == 0
    assert client.get(f'/api/applications/{other_app}', headers=leader).status_code == 403
    assert client.post('/api/applications', headers=leader, json={**BODY, 'portfolioId': other}).status_code == 403
    assert client.put(f'/api/applications/{own_app}', headers=leader, json={**BODY, 'portfolioId': other}).status_code == 403
    assert client.put(f'/api/applications/{other_app}', headers=leader, json={**BODY, 'portfolioId': assigned}).status_code == 403
    assert client.delete(f'/api/applications/{own_app}', headers=leader).status_code == 403
    assert client.post('/api/applications', headers=leader, json={**BODY, 'portfolioId': assigned}).status_code == 201
    db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    result = client.get('/api/applications', headers=leader)
    assert result.status_code == 200
    assert result.json()['total'] == 0


def test_direct_service_with_real_mongo():
    """Exercise domain operations and failures independently of HTTP."""
    async def scenario():
        mongo = AsyncMongoClient(URI)
        name = 'etsip_app_service_' + uuid.uuid4().hex
        db = mongo[name]
        try:
            await db.applications.create_index('name', unique=True)
            portfolio = (await db.portfolios.insert_one({'name': 'Test'})).inserted_id
            repo = ApplicationRepository(db)
            admin = {'_id': ObjectId(), 'name': 'Admin', 'role': 'Administrator'}
            data = ApplicationInput(**{**BODY, 'portfolioId': str(portfolio)})
            created = await create_application(repo, admin, data)
            identifier = created['id']
            assert (await db.applications.find_one({'_id': ObjectId(identifier)}))['qualityScore'] == 90
            with pytest.raises(HTTPException) as duplicate:
                await create_application(repo, admin, data)
            assert duplicate.value.status_code == 409
            assert await db.applications.count_documents({}) == 1
            leader = {'_id': ObjectId(), 'name': 'Leader', 'role': 'Portfolio Leader', 'portfolioAccess': []}
            assert (await list_applications(repo, leader, None, None, None, None, None, 25, 0))['total'] == 0
            with pytest.raises(HTTPException) as denied:
                await visible(repo, leader, identifier)
            assert denied.value.status_code == 403
            with pytest.raises(HTTPException) as denied_edit:
                await edit_application(repo, leader, identifier, ApplicationInput(**{**BODY, 'portfolioId': str(portfolio), 'qualityScore': 1}))
            assert denied_edit.value.status_code == 403
            assert (await db.applications.find_one({'_id': ObjectId(identifier)}))['qualityScore'] == 90
            leader['portfolioAccess'] = [str(portfolio)]
            assert (await edit_application(repo, leader, identifier, ApplicationInput(**{**BODY, 'portfolioId': str(portfolio), 'qualityScore': 10})))['qualityScore'] == 10
            assert (await db.applications.find_one({'_id': ObjectId(identifier)}))['qualityScore'] == 10
            await delete_application(repo, admin, identifier)
            assert await db.applications.find_one({'_id': ObjectId(identifier)}) is None
            assert [event['action'] async for event in db.audit_logs.find({'entityId': identifier})] == ['create', 'edit', 'delete']
            with pytest.raises(HTTPException) as missing:
                await visible(repo, admin, identifier)
            assert missing.value.status_code == 404
        finally:
            await mongo.drop_database(name)
            await mongo.close()
    asyncio.run(scenario())


def test_seed_idempotence(context):
    """Repeat seed without duplicating or resetting application data."""
    _, db = context
    db.applications.update_one({'name': 'Payment Gateway'}, {'$set': {'qualityScore': 12}})
    async def seed_again():
        from app.core.config import Settings
        from app.core.seed import seed_database
        mongo = AsyncMongoClient(URI)
        try:
            await seed_database(mongo[db.name], Settings())
        finally:
            await mongo.close()
    asyncio.run(seed_again())
    assert db.applications.count_documents({}) == 10
    assert db.applications.find_one({'name': 'Payment Gateway'})['qualityScore'] == 12


OMITTED = object()


@pytest.mark.parametrize('field', ['name', 'portfolioId'])
def test_required_application_fields_and_lengths(context, field):
    """Reject invalid required fields without changing MongoDB on create or edit."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    payload = {**BODY, 'portfolioId': portfolio}
    created = client.post('/api/applications', headers=admin, json=payload)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = db.applications.find_one({'_id': ObjectId(identifier)})
    count = db.applications.count_documents({})
    values = [OMITTED, None, '', '   ', 123, True, [], {'$ne': ''}]
    values += ['x' * 201, 'x' * 4001] if field == 'name' else ['a' * 23, 'a' * 25, str(ObjectId())]
    for value in values:
        body = dict(payload)
        if value is OMITTED:
            del body[field]
        else:
            body[field] = value
        for method, path in [('post', '/api/applications'), ('put', f'/api/applications/{identifier}')]:
            result = getattr(client, method)(path, headers=admin, json=body)
            assert result.status_code == 422, (field, value, method, result.text)
            assert db.applications.count_documents({}) == count
            assert db.applications.find_one({'_id': ObjectId(identifier)}) == before
    for name in ['N', 'N' * 200]:
        result = client.put(f'/api/applications/{identifier}', headers=admin, json={**payload, 'name': name})
        assert result.status_code == 200, result.text
        assert db.applications.find_one({'_id': ObjectId(identifier)})['name'] == name
    assert len(portfolio) == 24
    detail = client.get(f'/api/applications/{identifier}', headers=admin)
    assert detail.status_code == 200
    assert detail.json()['portfolioId'] == portfolio


@pytest.mark.parametrize('field', ['applicationHealthScore', 'qualityScore', 'automationCoverage', 'unitTestCoverage'])
def test_score_boundaries_and_types_on_create_and_edit(context, field):
    """Scores default to zero and accept only strict integers from 0 to 100."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    payload = {**BODY, 'portfolioId': portfolio}
    created = client.post('/api/applications', headers=admin, json=payload)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = db.applications.find_one({'_id': ObjectId(identifier)})
    count = db.applications.count_documents({})
    for value in [None, '', '100', True, 1.5, [], {'$gt': 0}, -1, 101, 10**10]:
        for method, path in [('post', '/api/applications'), ('put', f'/api/applications/{identifier}')]:
            result = getattr(client, method)(path, headers=admin, json={**payload, field: value})
            assert result.status_code == 422, (field, value, method, result.text)
            assert db.applications.count_documents({}) == count
            assert db.applications.find_one({'_id': ObjectId(identifier)}) == before
    for value in [OMITTED, 0, 100]:
        body = {**payload, 'name': f'{field}-{value if value is not OMITTED else "omitted"}'}
        if value is OMITTED:
            del body[field]
        else:
            body[field] = value
        expected = 0 if value is OMITTED else value
        result = client.post('/api/applications', headers=admin, json=body)
        assert result.status_code == 201, result.text
        assert result.json()[field] == expected
        assert db.applications.find_one({'_id': ObjectId(result.json()['id'])})[field] == expected
        result = client.put(f'/api/applications/{identifier}', headers=admin, json={**body, 'name': 'Inventory Test'})
        assert result.status_code == 200, result.text
        assert db.applications.find_one({'_id': ObjectId(identifier)})[field] == expected


@pytest.mark.parametrize('field', ['repositoryLink', 'pipelineLink'])
def test_url_boundaries_and_types_on_create_and_edit(context, field):
    """Optional URLs accept HTTP(S), null and omission, but not unsafe or oversized values."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    payload = {**BODY, 'portfolioId': portfolio}
    created = client.post('/api/applications', headers=admin, json=payload)
    assert created.status_code == 201
    identifier = created.json()['id']
    before = db.applications.find_one({'_id': ObjectId(identifier)})
    count = db.applications.count_documents({})
    prefix = 'https://example.com/'
    for value in ['', ' ', 123, True, [], {'$ne': ''}, 'javascript:alert(1)', 'ftp://example.com/', 'https://user:pass@example.com/', prefix + 'a' * (2084 - len(prefix))]:
        for method, path in [('post', '/api/applications'), ('put', f'/api/applications/{identifier}')]:
            result = getattr(client, method)(path, headers=admin, json={**payload, field: value})
            assert result.status_code == 422, (field, value, method, result.text)
            assert db.applications.count_documents({}) == count
            assert db.applications.find_one({'_id': ObjectId(identifier)}) == before
    for index, value in enumerate([OMITTED, None, 'http://example.com/', prefix + 'a' * (2083 - len(prefix))]):
        body = {**payload, 'name': f'{field}-{index}'}
        if value is OMITTED:
            del body[field]
        else:
            body[field] = value
        expected = None if value is OMITTED else value
        result = client.post('/api/applications', headers=admin, json=body)
        assert result.status_code == 201, result.text
        assert result.json()[field] == expected
        assert db.applications.find_one({'_id': ObjectId(result.json()['id'])})[field] == expected
        result = client.put(f'/api/applications/{identifier}', headers=admin, json={**body, 'name': 'Inventory Test'})
        assert result.status_code == 200, result.text
        assert db.applications.find_one({'_id': ObjectId(identifier)})[field] == expected


def test_operator_injection_and_literal_search(context):
    """Treat Mongo operators and regex metacharacters as data, not predicates."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    name = '{"$ne":""} .*'
    result = client.post('/api/applications', headers=admin, json={**BODY, 'name': name, 'portfolioId': portfolio})
    assert result.status_code == 201, result.text
    identifier = result.json()['id']
    for term in ['{"$ne":""}', '.*', name]:
        found = client.get('/api/applications', headers=admin, params={'search': term})
        assert found.status_code == 200
        assert found.json()['total'] == 1
        assert [item['id'] for item in found.json()['items']] == [identifier]
    result = client.get('/api/applications', headers=admin, params={'search': '{"$gt":""}'})
    assert result.status_code == 200
    assert result.json()['total'] == 0
    result = client.get('/api/applications', headers=admin, params={'portfolioId': '{"$ne":""}'})
    assert result.status_code == 200
    assert result.json()['total'] == 0
    rejected = client.post('/api/applications', headers=admin, json={**BODY, 'name': {'$ne': ''}, 'portfolioId': portfolio})
    assert rejected.status_code == 422
    assert db.applications.count_documents({}) == 11


def test_stored_xss_text_round_trip(context):
    """Persist and return untrusted text verbatim for safe client-side rendering."""
    client, db = context
    admin = admin_headers(client)
    portfolio = str(db.portfolios.find_one({'name': 'Payments'})['_id'])
    name = '<script>window.xss=1</script>'
    description = '<img src=x onerror="window.xss=1">'
    created = client.post('/api/applications', headers=admin, json={**BODY, 'name': name, 'description': description, 'portfolioId': portfolio})
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    stored = db.applications.find_one({'_id': ObjectId(identifier)})
    detail = client.get(f'/api/applications/{identifier}', headers=admin)
    assert detail.status_code == 200
    for item in [created.json(), stored, detail.json()]:
        assert item['name'] == name
        assert item['description'] == description
    found = client.get('/api/applications', headers=admin, params={'search': name})
    assert found.status_code == 200
    assert [(item['id'], item['name'], item['description']) for item in found.json()['items']] == [(identifier, name, description)]
