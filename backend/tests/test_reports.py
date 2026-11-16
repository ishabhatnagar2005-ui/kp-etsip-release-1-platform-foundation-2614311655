"""Exercise reports over HTTP against an isolated real MongoDB database."""
import csv
import io
import os
import uuid

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import app
from app.reports.service import csv_cell

URI = os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017')


@pytest.fixture
def context(monkeypatch):
    """Seed a separate database and clean it after each test."""
    name = 'etsip_reports_' + uuid.uuid4().hex
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
            alpha, beta = ObjectId(), ObjectId()
            db.portfolios.insert_many([
                {'_id': alpha, 'name': 'Alpha', 'owner': '=formula', 'productArea': 'One', 'description': '', 'status': 'Active', 'createdAt': 'now', 'updatedAt': 'now'},
                {'_id': beta, 'name': 'Beta', 'owner': 'Owner', 'productArea': 'Two', 'description': '', 'status': 'Archived', 'createdAt': 'now', 'updatedAt': 'now'},
            ])
            common = {'description': '  +danger', 'productArea': 'One', 'businessOwner': 'Owner', 'technologyOwner': '', 'etsOwner': '', 'criticality': 'High', 'tier': 2, 'lifecycleStatus': 'Active', 'technologyStack': '', 'repositoryLink': None, 'pipelineLink': None, 'applicationHealthScore': 70, 'qualityScore': 80, 'automationCoverage': 60, 'unitTestCoverage': 50, 'openDefects': 0, 'openCriticalDefects': 2, 'riskLevel': 'High', 'createdAt': 'now', 'updatedAt': 'now'}
            db.applications.insert_many([
                {**common, 'name': 'First', 'portfolioId': str(alpha)},
                {**common, 'name': 'Second', 'portfolioId': str(beta), 'riskLevel': 'Low', 'criticality': 'Low'},
            ])
            db.users.update_one({'role': 'Portfolio Leader'}, {'$set': {'portfolioAccess': [str(alpha)]}})
            yield client, db, str(alpha), str(beta)
    finally:
        mongo.drop_database(name)
        mongo.close()


def login(client, role='executive'):
    """Authenticate a seeded demo user."""
    response = client.post('/api/auth/login', json={'email': role + '@ketsip.local', 'password': 'First-demo-password-123'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['token']}


def rows(response):
    """Parse a CSV response with its header."""
    return list(csv.DictReader(io.StringIO(response.text)))


def test_tables_filters_and_pagination(context):
    """Return both matching table types with correct aggregates and pages."""
    client, _, alpha, _ = context
    auth = login(client)
    page = client.get('/api/reports/applications', headers=auth, params={'limit': 1, 'offset': 1}).json()
    assert page['total'] == 2 and page['items'][0]['name'] == 'Second'
    result = client.get('/api/reports/applications', headers=auth, params={'search': 'irst', 'portfolioId': alpha, 'criticality': 'High', 'riskLevel': 'High', 'lifecycleStatus': 'Active'}).json()
    assert [row['name'] for row in result['items']] == ['First']
    portfolios = client.get('/api/reports/portfolios', headers=auth, params={'status': 'Active', 'productArea': 'One', 'search': 'lph'}).json()
    assert portfolios['total'] == 1
    assert portfolios['items'][0]['applicationCount'] == 1 and portfolios['items'][0]['qualityScore'] == 80


def test_csv_full_columns_audit_and_filter_parity(context):
    """Export filtered inventory safely and persist a separate audit event per report."""
    client, db, alpha, _ = context
    auth = login(client)
    filters = {'search': 'First', 'portfolioId': alpha, 'criticality': 'High', 'riskLevel': 'High', 'lifecycleStatus': 'Active'}
    response = client.get('/api/reports/applications', headers=auth, params={**filters, 'format': 'csv', 'limit': 1, 'offset': 50})
    assert response.status_code == 200 and 'attachment' in response.headers['content-disposition']
    applications = rows(response)
    assert len(applications) == 1 and applications[0]['name'] == 'First'
    assert applications[0]['description'] == "'  +danger"
    assert applications[0]['openDefects'] == '0' and applications[0]['unitTestCoverage'] == '50'
    assert {'id', 'createdAt', 'updatedAt', 'businessOwner', 'repositoryLink'} <= applications[0].keys()
    response = client.get('/api/reports/portfolios', headers=auth, params={'format': 'csv', 'status': 'Active'})
    portfolio = rows(response)[0]
    assert portfolio['name'] == 'Alpha' and portfolio['owner'] == "'=formula"
    assert portfolio['applicationCount'] == '1' and portfolio['qualityScore'] == '80'
    assert {'id', 'description', 'productArea', 'createdAt', 'updatedAt'} <= portfolio.keys()
    events = list(db.audit_logs.find({'action': 'export'}))
    assert {event['entityType'] for event in events} == {'application', 'portfolio'}
    assert all(event['userId'] and event['timestamp'] and event['details'] for event in events)


def test_scope_for_tables_and_exports(context):
    """Constrain leaders even when they request an unassigned portfolio."""
    client, db, alpha, beta = context
    auth = login(client, 'leader')
    for kind in ('applications', 'portfolios'):
        assert len(client.get('/api/reports/' + kind, headers=auth).json()['items']) == 1
        assert len(rows(client.get('/api/reports/' + kind, headers=auth, params={'format': 'csv'}))) == 1
    assert client.get('/api/reports/applications', headers=auth, params={'portfolioId': beta}).json()['total'] == 0
    assert rows(client.get('/api/reports/applications', headers=auth, params={'portfolioId': beta, 'format': 'csv'})) == []
    db.users.update_one({'role': 'Portfolio Leader'}, {'$set': {'portfolioAccess': []}})
    assert client.get('/api/reports/portfolios', headers=auth).json()['total'] == 0
    assert rows(client.get('/api/reports/applications', headers=auth, params={'format': 'csv'})) == []


def test_permissions_and_validation(context):
    """Enforce separate stored view and export permissions and validate inputs."""
    client, db, _, _ = context
    for kind in ('applications', 'portfolios'):
        path = '/api/reports/' + kind
        assert client.get(path).status_code == 401
        readonly = login(client, 'readonly')
        assert client.get(path, headers=readonly).status_code == 200
        db.roles.update_one({'name': 'Read Only'}, {'$addToSet': {'permissions': 'export'}})
        assert client.get(path, headers=readonly, params={'format': 'csv'}).status_code == 403
        auth = login(client)
        assert client.get(path, headers=auth, params={'format': 'xlsx'}).status_code == 422
        assert client.get(path, headers=auth, params={'unexpected': 'x'}).status_code == 422
        assert client.get(path, headers=auth, params={'limit': 101}).status_code == 422
    assert client.get('/api/reports/applications', headers=auth, params={'riskLevel': 'Extreme'}).status_code == 422
    assert client.get('/api/reports/portfolios', headers=auth, params={'status': 'Invalid'}).status_code == 422
    db.roles.update_one({'name': 'Executive'}, {'$pull': {'permissions': 'view'}})
    assert client.get('/api/reports/applications', headers=auth).status_code == 403
    assert client.get('/api/reports/applications', headers=auth, params={'format': 'csv'}).status_code == 200
    db.roles.update_one({'name': 'Executive'}, {'$pull': {'permissions': 'export'}})
    assert client.get('/api/reports/portfolios', headers=auth, params={'format': 'csv'}).status_code == 403


def test_export_spans_multiple_pages(context):
    """Export all matching rows rather than only the first list page."""
    client, db, alpha, _ = context
    template = db.applications.find_one({'name': 'First'})
    template.pop('_id')
    db.applications.insert_many([{**template, 'name': f'Bulk {index:03}'} for index in range(105)])
    auth = login(client)
    response = client.get('/api/reports/applications', headers=auth, params={'format': 'csv', 'portfolioId': alpha, 'limit': 1})
    assert response.status_code == 200
    exported = rows(response)
    assert len(exported) == 106
    assert {'Bulk 000', 'Bulk 104', 'First'} <= {row['name'] for row in exported}


def test_csv_injection_cells():
    """Protect formula triggers and preserve numeric zero."""
    for value in ('=1', ' +1', '-1', '@x', '\ttext', '  \ttext', '\rtext', '\ntext'):
        assert csv_cell(value).startswith("'")
    assert csv_cell(0) == '0' and csv_cell(None) == '' and csv_cell('ordinary') == 'ordinary'


def test_export_cap(context, monkeypatch):
    """Reject oversized exports rather than silently truncating or auditing them."""
    client, db, _, _ = context
    monkeypatch.setattr('app.reports.service.MAX_EXPORT_ROWS', 1)
    auth = login(client)
    for kind in ('applications', 'portfolios'):
        response = client.get('/api/reports/' + kind, headers=auth, params={'format': 'csv'})
        assert response.status_code == 422
    assert db.audit_logs.count_documents({'action': 'export'}) == 0
