"""Verify dashboard calculations and authorization against real MongoDB."""
import asyncio
import os
import uuid

import pytest
from bson import ObjectId
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import AsyncMongoClient, MongoClient

from app.dashboard.repository import DashboardRepository
from app.dashboard.service import average, executive_dashboard
from app.main import app

URI = os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')


@pytest.fixture
def context(monkeypatch):
    """Create a seeded isolated database with deterministic dashboard data."""
    name = 'etsip_dashboard_' + uuid.uuid4().hex
    monkeypatch.setenv('MONGODB_DB', name)
    monkeypatch.setenv('JWT_SECRET', 'test-secret-with-more-than-thirty-two-characters')
    monkeypatch.setenv('ADMIN_PASSWORD', 'First-admin-password-123')
    monkeypatch.setenv('DEMO_PASSWORD', 'First-demo-password-123')
    monkeypatch.setenv('SEED_ON_STARTUP', 'true')
    mongo = MongoClient(URI)
    try:
        with TestClient(app) as client:
            db = mongo[name]
            db.applications.delete_many({})
            db.portfolios.delete_many({})
            alpha, beta, empty = [ObjectId() for _ in range(3)]
            db.portfolios.insert_many([{'_id': alpha, 'name': 'Alpha'}, {'_id': beta, 'name': 'Beta'}, {'_id': empty, 'name': 'Empty'}])
            db.applications.insert_many([
                {'name': 'First', 'portfolioId': str(alpha), 'productArea': 'One', 'qualityScore': 80, 'applicationHealthScore': 50, 'automationCoverage': 20, 'openCriticalDefects': 2, 'riskLevel': 'High'},
                {'name': 'Second', 'portfolioId': str(alpha), 'productArea': 'Two', 'qualityScore': 81, 'applicationHealthScore': 51, 'automationCoverage': 21, 'openCriticalDefects': 3, 'riskLevel': 'Low'},
                {'name': 'Third', 'portfolioId': str(beta), 'productArea': 'One', 'qualityScore': 20, 'applicationHealthScore': 70, 'automationCoverage': 90, 'openCriticalDefects': 5, 'riskLevel': 'High'},
            ])
            db.users.update_one({'role': 'Portfolio Leader'}, {'$set': {'portfolioAccess': [str(alpha)]}})
            yield client, db, alpha, beta, empty
    finally:
        mongo.drop_database(name)
        mongo.close()


def login(client, role='executive'):
    """Authenticate a seeded non-administrator user."""
    response = client.post('/api/auth/login', json={'email': role + '@ketsip.local', 'password': 'First-demo-password-123'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def test_exact_metrics_and_filters(context):
    """Check every formula, all filters, combined filters and empty portfolios."""
    client, _, alpha, beta, empty = context
    auth = login(client)
    response = client.get('/api/dashboard/executive', headers=auth)
    assert response.status_code == 200
    assert response.json() == {
        'enterpriseQualityScore': 60, 'applicationHealthScore': 57, 'automationMaturityScore': 44,
        'openCriticalDefects': 10, 'applicationsAtRisk': 2, 'totalApplications': 3, 'totalPortfolios': 3,
        'portfolios': [
            {'id': str(alpha), 'name': 'Alpha', 'applicationCount': 2, 'qualityScore': 81, 'applicationsAtRisk': 1},
            {'id': str(beta), 'name': 'Beta', 'applicationCount': 1, 'qualityScore': 20, 'applicationsAtRisk': 1},
            {'id': str(empty), 'name': 'Empty', 'applicationCount': 0, 'qualityScore': None, 'applicationsAtRisk': 0},
        ],
    }
    response = client.get('/api/dashboard/executive', headers=auth, params={'portfolioId': str(alpha)})
    assert response.status_code == 200
    filtered = response.json()
    assert (filtered['totalPortfolios'], filtered['totalApplications'], filtered['enterpriseQualityScore'], filtered['applicationHealthScore'], filtered['automationMaturityScore']) == (1, 2, 81, 51, 21)
    response = client.get('/api/dashboard/executive', headers=auth, params={'productArea': 'One'})
    assert response.status_code == 200
    filtered = response.json()
    assert (filtered['totalPortfolios'], filtered['totalApplications'], filtered['enterpriseQualityScore'], filtered['openCriticalDefects']) == (2, 2, 50, 7)
    response = client.get('/api/dashboard/executive', headers=auth, params={'riskLevel': 'Low'})
    assert response.status_code == 200
    filtered = response.json()
    assert (filtered['totalPortfolios'], filtered['totalApplications'], filtered['applicationsAtRisk']) == (1, 1, 0)
    response = client.get('/api/dashboard/executive', headers=auth, params={'portfolioId': str(alpha), 'productArea': 'One', 'riskLevel': 'High'})
    assert response.status_code == 200
    filtered = response.json()
    assert (filtered['enterpriseQualityScore'], filtered['openCriticalDefects'], filtered['applicationsAtRisk']) == (80, 2, 1)
    response = client.get('/api/dashboard/executive', headers=auth, params={'productArea': 'missing'})
    assert response.status_code == 200
    filtered = response.json()
    assert filtered == {'enterpriseQualityScore': None, 'applicationHealthScore': None, 'automationMaturityScore': None, 'openCriticalDefects': 0, 'applicationsAtRisk': 0, 'totalApplications': 0, 'totalPortfolios': 0, 'portfolios': []}
    response = client.get('/api/dashboard/executive', headers=auth, params={'portfolioId': str(empty)})
    assert response.status_code == 200
    filtered = response.json()
    assert filtered['totalPortfolios'] == 1 and filtered['enterpriseQualityScore'] is None


def test_authorization_scope_and_validation(context):
    """Reject missing permissions and constrain leaders even with explicit filters."""
    client, db, alpha, beta, _ = context
    assert client.get('/api/dashboard/executive').status_code == 401
    assert client.get('/api/dashboard/executive', headers={'Authorization': 'Bearer invalid'}).status_code == 401
    leader = login(client, 'leader')
    response = client.get('/api/dashboard/executive', headers=leader)
    assert response.status_code == 200
    result = response.json()
    assert result['totalApplications'] == 2 and result['totalPortfolios'] == 1
    assert result['portfolios'][0]['id'] == str(alpha)
    response = client.get('/api/dashboard/executive', headers=leader, params={'portfolioId': str(beta)})
    assert response.status_code == 200
    assert response.json()['totalApplications'] == 0
    db.users.update_one({'role': 'Portfolio Leader'}, {'$set': {'portfolioAccess': []}})
    response = client.get('/api/dashboard/executive', headers=leader)
    assert response.status_code == 200
    assert response.json()['totalPortfolios'] == 0
    assert client.get('/api/dashboard/executive', headers=leader, params={'portfolioId': 'not-id'}).status_code == 422
    assert client.get('/api/dashboard/executive', headers=leader, params={'riskLevel': 'Critical'}).status_code == 422
    assert client.get('/api/dashboard/executive', headers=leader, params={'portfolioId': ''}).status_code == 422
    db.roles.update_one({'name': 'Portfolio Leader'}, {'$pull': {'permissions': 'view'}})
    assert client.get('/api/dashboard/executive', headers=leader).status_code == 403


def test_service_real_mongo(context):
    """Exercise service calculations and invalid inputs without the HTTP layer."""
    _, db, alpha, _, _ = context
    async def scenario():
        mongo = AsyncMongoClient(URI)
        try:
            repo = DashboardRepository(mongo[db.name])
            result = await executive_dashboard(repo, {'role': 'Portfolio Leader', 'portfolioAccess': [str(alpha)]})
            assert result['enterpriseQualityScore'] == 81
            assert result['openCriticalDefects'] == 5
            assert (await executive_dashboard(repo, {'role': 'Portfolio Leader', 'portfolioAccess': []}))['enterpriseQualityScore'] is None
            with pytest.raises(HTTPException):
                await executive_dashboard(repo, {'role': 'Executive'}, 'bad')
            with pytest.raises(HTTPException):
                await executive_dashboard(repo, {'role': 'Executive'}, risk_level='Bad')
        finally:
            await mongo.close()
    asyncio.run(scenario())
    assert average(1, 2) == 1 and average(0, 0) is None
