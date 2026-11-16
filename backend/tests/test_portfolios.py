"""Exercise portfolio service and HTTP behavior against real MongoDB."""
import asyncio
import os
import uuid
import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient
from app.main import app
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schema import PortfolioInput
from app.portfolios.service import create_portfolio, delete_portfolio, edit_portfolio, list_portfolios, visible

URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
BODY = {"name": "New Portfolio", "owner": "Alex", "description": "Quality", "productArea": "Digital", "status": "Active"}


@pytest.fixture
def context(monkeypatch):
    """Start the app using a unique disposable Mongo database."""
    name = "etsip_portfolios_" + uuid.uuid4().hex
    monkeypatch.setenv("MONGODB_DB", name)
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-more-than-thirty-two-characters")
    monkeypatch.setenv("ADMIN_PASSWORD", "First-admin-password-123")
    monkeypatch.setenv("DEMO_PASSWORD", "First-demo-password-123")
    monkeypatch.setenv("SEED_ON_STARTUP", "true")
    mongo = MongoClient(URI)
    try:
        with TestClient(app) as client:
            yield client, mongo[name]
    finally:
        mongo.drop_database(name)
        mongo.close()


def headers(client, role, password="First-demo-password-123"):
    """Authenticate a seeded account."""
    response = client.post('/api/auth/login', json={'email': role + '@ketsip.local', 'password': password})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def admin_headers(client):
    """Complete the enforced first-use password change."""
    initial = headers(client, 'admin', 'First-admin-password-123')
    assert client.get('/api/portfolios', headers=initial).status_code == 403
    assert client.put('/api/auth/password', headers=initial, json={'currentPassword': 'First-admin-password-123', 'newPassword': 'Replacement-password-456'}).status_code == 204
    return headers(client, 'admin', 'Replacement-password-456')


def test_api_crud_filters_aggregates_audit_and_linked_applications(context):
    """Persist writes, search, aggregate linked data, and reject unsafe deletion."""
    client, db = context
    assert client.get('/api/portfolios').status_code == 401
    admin = admin_headers(client)
    assert db.portfolios.count_documents({}) == 3
    created = client.post('/api/portfolios', headers=admin, json=BODY)
    assert created.status_code == 201
    identifier = created.json()['id']
    assert db.portfolios.find_one({'_id': ObjectId(identifier)})['name'] == BODY['name']
    assert created.json()['qualityScore'] is None
    assert client.post('/api/portfolios', headers=admin, json=BODY).status_code == 409
    assert client.post('/api/portfolios', headers=admin, json={**BODY, 'name': ' '}).status_code == 422
    db.applications.insert_many([{'name': 'One', 'portfolioId': identifier, 'qualityScore': 80}, {'name': 'Two', 'portfolioId': identifier, 'qualityScore': 91}])
    result = client.get('/api/portfolios', headers=admin, params={'search': 'new', 'status': 'Active', 'productArea': 'Digital', 'limit': 1, 'offset': 0})
    assert result.status_code == 200
    assert result.json()['total'] == 1 and result.json()['items'][0]['qualityScore'] == 86
    assert result.json()['items'][0]['applicationCount'] == 2
    assert client.get('/api/portfolios', headers=admin, params={'search': '.*'}).json()['total'] == 0
    assert client.get('/api/portfolios', headers=admin, params={'limit': 101}).status_code == 422
    assert client.get('/api/portfolios', headers=admin, params={'offset': -1}).status_code == 422
    assert client.get('/api/portfolios', headers=admin, params={'status': 'Invalid'}).status_code == 422
    assert client.get('/api/portfolios', headers=admin, params={'productArea': 'Other'}).json()['total'] == 0
    assert client.get('/api/portfolios', headers=admin, params={'search': 'New', 'offset': 1}).json()['items'] == []
    assert client.put(f'/api/portfolios/{identifier}', headers=admin, json={**BODY, 'name': 'Payments'}).status_code == 409
    assert client.get('/api/portfolios/not-an-id/applications', headers=admin).status_code == 404
    linked = client.get(f'/api/portfolios/{identifier}/applications?limit=1&offset=1', headers=admin).json()
    assert linked['total'] == 2 and linked['items'][0]['name'] == 'Two'
    assert client.delete(f'/api/portfolios/{identifier}', headers=admin).status_code == 409
    updated = client.put(f'/api/portfolios/{identifier}', headers=admin, json={**BODY, 'status': 'Archived'})
    assert updated.status_code == 200 and db.portfolios.find_one({'_id': ObjectId(identifier)})['status'] == 'Archived'
    assert client.get(f'/api/portfolios/{identifier}', headers=admin).json()['status'] == 'Archived'
    db.applications.delete_many({'portfolioId': identifier})
    assert client.delete(f'/api/portfolios/{identifier}', headers=admin).status_code == 204
    assert client.get(f'/api/portfolios/{identifier}', headers=admin).status_code == 404
    assert [entry['action'] for entry in db.audit_logs.find({'entityType': 'portfolio', 'entityId': identifier})] == ['create', 'edit', 'delete']
    assert client.put('/api/portfolios/not-an-id', headers=admin, json=BODY).status_code == 404
    assert client.delete('/api/portfolios/not-an-id', headers=admin).status_code == 404


def test_role_scope_and_stored_permission_restrictions(context):
    """Intersect editable permissions with immutable roles and leader scope."""
    client, db = context
    leader = headers(client, 'leader')
    visible_list = client.get('/api/portfolios', headers=leader).json()
    assert visible_list['total'] == 1
    assigned = visible_list['items'][0]['id']
    other = str(db.portfolios.find_one({'name': 'Customer Platform'})['_id'])
    assert client.get(f'/api/portfolios/{other}', headers=leader).status_code == 403
    assert client.get(f'/api/portfolios/{other}/applications', headers=leader).status_code == 403
    assert client.put(f'/api/portfolios/{other}', headers=leader, json=BODY).status_code == 403
    assert client.put(f'/api/portfolios/{assigned}', headers=leader, json={**BODY, 'name': 'Payments'}).status_code == 200
    assert client.post('/api/portfolios', headers=leader, json=BODY).status_code == 403
    assert client.delete(f'/api/portfolios/{assigned}', headers=leader).status_code == 403
    for role in ['engineer', 'executive', 'auditor', 'readonly']:
        token = headers(client, role)
        assert client.get('/api/portfolios', headers=token).json()['total'] == 3
        assert client.post('/api/portfolios', headers=token, json=BODY).status_code == 403
        assert client.put(f'/api/portfolios/{assigned}', headers=token, json=BODY).status_code == 403
        assert client.delete(f'/api/portfolios/{assigned}', headers=token).status_code == 403
    db.roles.update_one({'name': 'Portfolio Leader'}, {'$pull': {'permissions': 'edit'}})
    assert client.put(f'/api/portfolios/{assigned}', headers=leader, json=BODY).status_code == 403
    db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    assert client.get('/api/portfolios', headers=leader).json()['total'] == 0


def test_service_directly_persists_and_rejects_invalid_operations():
    """Exercise service rules independently of HTTP with a real database."""
    async def scenario():
        client = AsyncMongoClient(URI)
        name = 'etsip_portfolio_service_' + uuid.uuid4().hex
        db = client[name]
        try:
            await db.portfolios.create_index('name', unique=True)
            repo = PortfolioRepository(db)
            admin = {'_id': ObjectId(), 'name': 'Admin', 'role': 'Administrator'}
            data = PortfolioInput(**BODY)
            created = await create_portfolio(repo, admin, data)
            identifier = created['id']
            with pytest.raises(HTTPException) as duplicate:
                await create_portfolio(repo, admin, data)
            assert duplicate.value.status_code == 409
            leader = {'_id': ObjectId(), 'name': 'Leader', 'role': 'Portfolio Leader', 'portfolioAccess': []}
            assert (await list_portfolios(repo, leader, None, None, None, 25, 0))['total'] == 0
            with pytest.raises(HTTPException) as denied:
                await visible(repo, leader, identifier)
            assert denied.value.status_code == 403
            leader['portfolioAccess'] = [identifier]
            assert (await edit_portfolio(repo, leader, identifier, PortfolioInput(**{**BODY, 'owner': 'Changed'})))['owner'] == 'Changed'
            await delete_portfolio(repo, admin, identifier)
            with pytest.raises(HTTPException) as missing:
                await visible(repo, admin, identifier)
            assert missing.value.status_code == 404
        finally:
            await client.drop_database(name)
            await client.close()
    asyncio.run(scenario())


def test_seed_is_idempotent_and_does_not_restore_removed_assignment(context):
    """Restart seeding without duplicating portfolios or overwriting access edits."""
    _, db = context
    assert len(db.users.find_one({'email': 'leader@ketsip.local'})['portfolioAccess']) == 1
    db.users.update_one({'email': 'leader@ketsip.local'}, {'$set': {'portfolioAccess': []}})
    async def seed_again():
        from app.core.config import Settings
        from app.core.seed import seed_database
        mongo = AsyncMongoClient(URI)
        try:
            await seed_database(mongo[db.name], Settings())
        finally:
            await mongo.close()
    asyncio.run(seed_again())
    assert db.portfolios.count_documents({}) == 3
    assert db.users.find_one({'email': 'leader@ketsip.local'})['portfolioAccess'] == []
