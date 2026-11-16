"""Exercise administration against an isolated MongoDB database."""
import asyncio
import csv
import io
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.main import app


@pytest.fixture(scope='module')
def env():
    """Use a unique database and remove it after tests."""
    from app.core.config import Settings

    dbname = 'etsip_admin_test_' + uuid.uuid4().hex
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('MONGODB_DB', dbname)
        patch.setenv('JWT_SECRET', 'test-secret-with-more-than-thirty-two-characters')
        patch.setenv('ADMIN_PASSWORD', 'First-admin-password-123')
        patch.setenv('DEMO_PASSWORD', 'First-demo-password-123')
        patch.setenv('SEED_ON_STARTUP', 'true')
        mongo = MongoClient(Settings().mongodb_uri)
        try:
            with TestClient(app) as client:
                db = mongo[dbname]
                db.users.update_one({'role': 'Administrator'}, {'$set': {'mustChangePassword': False}})
                yield client, db
        finally:
            mongo.drop_database(dbname)
            mongo.close()


def headers(client, email='admin@ketsip.local', password='First-admin-password-123'):
    """Sign in through the actual authentication route."""
    result = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert result.status_code == 200
    return {'Authorization': 'Bearer ' + result.json()['token']}


def test_users_lifecycle_and_last_admin(env):
    """Cover user creation, detail, edit, deactivation, validation and persistence."""
    client, db = env
    admin = headers(client)
    assert client.get('/api/users').status_code == 401
    assert client.get('/api/users', headers=admin, params={'limit': 101}).status_code == 422
    assert client.get('/api/users/bad', headers=admin).status_code == 404
    response = client.get('/api/auth/me', headers=admin)
    assert response.status_code == 200
    me = response.json()
    assert 'administer' in me['effectivePermissions']
    assert client.delete('/api/users/' + me['id'], headers=admin).status_code == 409
    portfolio = str(db.portfolios.find_one()['_id'])
    body = {'name': 'Test Person', 'email': 'TEST@ketsip.local', 'password': 'Strong-password-123', 'role': 'Engineer', 'portfolioAccess': [portfolio], 'status': 'Active', 'managerName': 'Manager', 'vendorIndicator': True}
    assert client.post('/api/users', headers=admin, json={**body, 'portfolioAccess': ['bad']}).status_code == 422
    assert client.post('/api/users', headers=admin, json={**body, 'password': 'short'}).status_code == 422
    created = client.post('/api/users', headers=admin, json=body)
    assert created.status_code == 201
    user = created.json()
    assert user['email'] == 'test@ketsip.local' and user['vendorIndicator'] is True
    assert 'password' not in user and 'passwordHash' not in user
    assert db.users.find_one({'email': user['email']})['passwordHash'] != body['password']
    assert client.post('/api/users', headers=admin, json=body).status_code == 409
    response = client.get('/api/users/' + user['id'], headers=admin)
    assert response.status_code == 200
    assert response.json()['managerName'] == 'Manager'
    update = {key: value for key, value in body.items() if key != 'password'}
    update.update(role='Auditor', name='Changed')
    response = client.put('/api/users/' + user['id'], headers=admin, json=update)
    assert response.status_code == 200
    assert response.json()['role'] == 'Auditor'
    response = client.get('/api/users/' + user['id'], headers=admin)
    assert response.status_code == 200
    assert response.json()['name'] == 'Changed'
    assert client.delete('/api/users/' + user['id'], headers=admin).status_code == 204
    response = client.get('/api/users/' + user['id'], headers=admin)
    assert response.status_code == 200
    assert response.json()['status'] == 'Inactive'
    assert client.post('/api/auth/login', json={'email': user['email'], 'password': body['password']}).status_code == 401
    events = list(db.audit_logs.find({'entityId': user['id']}))
    assert {'create', 'edit', 'roleChange', 'delete'} <= {event['action'] for event in events}
    assert body['password'] not in str(events)


def test_roles_fixed_scope_and_audit_filters_export(env):
    """Verify fixed roles, permission intersection, auditor access, and audit CSV."""
    client, db = env
    admin = headers(client)
    auditor = headers(client, 'auditor@ketsip.local', 'First-demo-password-123')
    engineer = headers(client, 'engineer@ketsip.local', 'First-demo-password-123')
    assert client.get('/api/users', headers=auditor).status_code == 403
    assert client.get('/api/roles', headers=auditor).status_code == 403
    assert client.get('/api/audit-logs', headers=engineer).status_code == 403
    response = client.get('/api/roles', headers=admin)
    assert response.status_code == 200
    roles = response.json()['items']
    assert len(roles) == 6
    role = next(r for r in roles if r['name'] == 'Engineer')
    payload = {'name': role['name'], 'description': 'Updated', 'permissions': ['view', 'administer', 'delete']}
    assert client.post('/api/roles', headers=admin, json=payload).status_code == 409
    assert client.post('/api/roles', headers=admin, json={**payload, 'name': 'Other'}).status_code == 422
    assert client.put('/api/roles/' + role['id'], headers=admin, json={**payload, 'permissions': ['bad']}).status_code == 422
    assert client.put('/api/roles/' + role['id'], headers=admin, json={**payload, 'name': 'Auditor'}).status_code == 409
    assert client.put('/api/roles/bad', headers=admin, json=payload).status_code == 404
    assert client.put('/api/roles/' + role['id'], headers=admin, json=payload).status_code == 200
    assert client.get('/api/users', headers=engineer).status_code == 403
    response = client.get('/api/auth/me', headers=engineer)
    assert response.status_code == 200
    assert response.json()['effectivePermissions'] == ['view']
    adminrole = next(r for r in roles if r['name'] == 'Administrator')
    assert client.put('/api/roles/' + adminrole['id'], headers=admin, json={'name': 'Administrator', 'description': '', 'permissions': ['view']}).status_code == 409
    response = client.get('/api/auth/me', headers=admin)
    assert response.status_code == 200
    me = response.json()
    today = datetime.now(timezone.utc).date().isoformat()
    query = {'userId': me['id'], 'action': 'permissionChange', 'from': today, 'to': today}
    events = client.get('/api/audit-logs', headers=auditor, params=query)
    assert events.status_code == 200
    assert events.json()['total'] >= 1
    assert all(e['action'] == 'permissionChange' and e['userId'] == me['id'] for e in events.json()['items'])
    assert client.get('/api/audit-logs', headers=auditor, params={'from': 'bad'}).status_code == 422
    assert client.get('/api/audit-logs', headers=auditor, params={'from': '2030-01-01', 'to': '2020-01-01'}).status_code == 422
    csv = client.get('/api/audit-logs/export', headers=auditor, params=query)
    assert csv.status_code == 200
    assert 'permissionChange' in csv.text and 'timestamp,userId' in csv.text
    assert client.get('/api/audit-logs/export', headers=engineer).status_code == 403
    assert db.audit_logs.count_documents({'action': 'export', 'entityType': 'audit'}) == 1
    assert client.put('/api/roles/' + role['id'], headers=admin, json={k: role[k] for k in ('name', 'description', 'permissions')}).status_code == 200


def test_create_missing_fixed_role(env):
    """Create a legitimately absent role, then restore the original definition."""
    client, db = env
    admin = headers(client)
    role = db.roles.find_one_and_delete({'name': 'Read Only'})
    try:
        response = client.post('/api/roles', headers=admin, json={'name': 'Read Only', 'description': 'Restored', 'permissions': ['view']})
        assert response.status_code == 201
        assert db.roles.find_one({'name': 'Read Only'})['permissions'] == ['view']
    finally:
        db.roles.delete_one({'name': 'Read Only'})
        db.roles.insert_one(role)


def test_admin_endpoints_auth_and_invalid_ids(env):
    """All management and audit endpoints require a suitable authenticated role."""
    client, _ = env
    engineer = headers(client, 'engineer@ketsip.local', 'First-demo-password-123')
    admin = headers(client)
    user = {'name': 'Auth Test', 'email': 'auth-test@example.com', 'password': 'Strong-password-123', 'role': 'Engineer'}
    role = {'name': 'Engineer', 'description': '', 'permissions': ['view']}
    paths = [('GET', '/api/users', None), ('GET', '/api/users/bad', None),
             ('POST', '/api/users', user), ('PUT', '/api/users/bad', {k: v for k, v in user.items() if k != 'password'}),
             ('DELETE', '/api/users/bad', None), ('GET', '/api/roles', None),
             ('POST', '/api/roles', role), ('PUT', '/api/roles/bad', role),
             ('GET', '/api/audit-logs', None), ('GET', '/api/audit-logs/export', None)]
    for method, path, body in paths:
        assert client.request(method, path, json=body).status_code == 401
        assert client.request(method, path, headers=engineer, json=body).status_code == 403
    for identifier in ('bad', '000000000000000000000000'):
        assert client.get('/api/users/' + identifier, headers=admin).status_code == 404
        assert client.put('/api/users/' + identifier, headers=admin, json={k: v for k, v in user.items() if k != 'password'}).status_code == 404
        assert client.delete('/api/users/' + identifier, headers=admin).status_code == 404
        assert client.put('/api/roles/' + identifier, headers=admin, json=role).status_code == 404
    for path in ('/api/users', '/api/roles', '/api/audit-logs'):
        assert client.get(path, headers=admin, params={'limit': 0}).status_code == 422
        assert client.get(path, headers=admin, params={'offset': -1}).status_code == 422


def test_user_validation_pagination_and_last_admin(env):
    """Validate assignments, duplicate edits, safe lists, and admin retention."""
    client, db = env
    admin = headers(client)
    portfolio = str(db.portfolios.find_one()['_id'])
    body = {'name': 'Validation Person', 'email': 'validation@example.com', 'role': 'Engineer', 'password': 'Strong-password-123', 'portfolioAccess': [portfolio]}
    for access in (['bad'], ['000000000000000000000000'], [portfolio, portfolio]):
        assert client.post('/api/users', headers=admin, json={**body, 'portfolioAccess': access}).status_code == 422
    assert client.post('/api/users', headers=admin, json={**body, 'email': 'not-an-email'}).status_code == 422
    assert client.post('/api/users', headers=admin, json={**body, 'role': 'Unknown'}).status_code == 422
    created = client.post('/api/users', headers=admin, json=body)
    assert created.status_code == 201
    uid = created.json()['id']
    update = {k: v for k, v in body.items() if k != 'password'}
    assert client.put('/api/users/' + uid, headers=admin, json={**update, 'email': 'admin@ketsip.local'}).status_code == 409
    assert client.put('/api/users/' + uid, headers=admin, json={**update, 'portfolioAccess': ['000000000000000000000000']}).status_code == 422
    assert db.users.find_one({'email': body['email']})['portfolioAccess'] == [portfolio]
    response = client.get('/api/users', headers=admin, params={'limit': 2, 'offset': 1})
    assert response.status_code == 200
    listing = response.json()
    assert listing['limit'] == 2 and listing['offset'] == 1 and len(listing['items']) == 2 and listing['total'] > 2
    assert all('passwordHash' not in item and 'password' not in item for item in listing['items'])
    response = client.get('/api/auth/me', headers=admin)
    assert response.status_code == 200
    me = response.json()
    admin_doc = db.users.find_one({'email': 'admin@ketsip.local'})
    admin_update = {key: admin_doc.get(key) for key in ('name', 'email', 'role', 'portfolioAccess', 'status', 'managerName', 'vendorIndicator', 'defaultLandingPage')}
    assert client.put('/api/users/' + me['id'], headers=admin, json={**admin_update, 'role': 'Engineer'}).status_code == 409
    assert client.put('/api/users/' + me['id'], headers=admin, json={**admin_update, 'status': 'Inactive'}).status_code == 409
    assert db.users.find_one({'_id': admin_doc['_id']})['status'] == 'Active'


def test_administrator_cannot_deactivate_own_account_with_another_admin(env):
    """Self-deactivation must be rejected independently of the last-admin guard."""
    client, db = env
    admin = headers(client)
    response = client.get('/api/auth/me', headers=admin)
    assert response.status_code == 200
    me = response.json()
    original = db.users.find_one({'email': 'admin@ketsip.local'})
    second = client.post('/api/users', headers=admin, json={'name': 'Second Admin', 'email': 'second-admin@example.com', 'password': 'Strong-password-123', 'role': 'Administrator'})
    assert second.status_code == 201
    try:
        response = client.delete('/api/users/' + me['id'], headers=admin)
        assert response.status_code == 409
        assert db.users.find_one({'_id': original['_id']})['status'] == 'Active'
    finally:
        db.users.update_one({'_id': original['_id']}, {'$set': {'status': original['status'], 'tokenVersion': original.get('tokenVersion', 0)}})
        db.users.delete_one({'email': 'second-admin@example.com'})


def test_leader_scope_and_fixed_role_limits_after_grant(env):
    """Editable grants cannot expand leader powers or portfolio visibility."""
    client, db = env
    admin = headers(client)
    leader = headers(client, 'leader@ketsip.local', 'First-demo-password-123')
    role = db.roles.find_one({'name': 'Portfolio Leader'})
    original = {key: role[key] for key in ('name', 'description', 'permissions')}
    role_id = str(role['_id'])
    try:
        grant = {**original, 'permissions': ['view', 'create', 'edit', 'delete', 'export', 'administer']}
        assert client.put('/api/roles/' + role_id, headers=admin, json=grant).status_code == 200
        assert db.roles.find_one({'_id': role['_id']})['permissions'] == grant['permissions']
        assert client.get('/api/users', headers=leader).status_code == 403
        assert client.get('/api/audit-logs', headers=leader).status_code == 403
        assigned = db.users.find_one({'email': 'leader@ketsip.local'})['portfolioAccess'][0]
        other = str(db.portfolios.find_one({'_id': {'$ne': db.portfolios.find_one({'name': 'Payments'})['_id']}})['_id'])
        visible = client.get('/api/portfolios', headers=leader)
        assert visible.status_code == 200
        assert [p['id'] for p in visible.json()['items']] == [assigned]
        assert client.get('/api/portfolios/' + assigned, headers=leader).status_code == 200
        assert client.get('/api/portfolios/' + other, headers=leader).status_code == 403
        assert client.delete('/api/portfolios/' + assigned, headers=leader).status_code == 403
    finally:
        assert client.put('/api/roles/' + role_id, headers=admin, json=original).status_code == 200


def test_audit_filter_boundaries_csv_and_validation(env):
    """Filter exact seeded events by user/action/date and protect CSV cells."""
    client, db = env
    auditor = headers(client, 'auditor@ketsip.local', 'First-demo-password-123')
    marker = uuid.uuid4().hex
    docs = [dict(timestamp=stamp, userId=actor, userName='=formula', action=action, entityType='user', entityId=marker, details='=unsafe')
            for stamp, actor, action in [('2024-04-10T00:00:00+00:00', marker, 'edit'), ('2024-04-10T23:59:59+00:00', marker, 'edit'), ('2024-04-11T00:00:00+00:00', marker, 'edit'), ('2024-04-10T12:00:00+00:00', 'another', 'edit'), ('2024-04-10T12:00:00+00:00', marker, 'create')]]
    db.audit_logs.insert_many(docs)
    query = {'userId': marker, 'action': 'edit', 'from': '2024-04-10', 'to': '2024-04-10'}
    result = client.get('/api/audit-logs', headers=auditor, params=query)
    assert result.status_code == 200
    assert result.json()['total'] == 2
    assert all(item['userId'] == marker and item['action'] == 'edit' for item in result.json()['items'])
    instant = client.get('/api/audit-logs', headers=auditor, params={**query, 'from': '2024-04-10T01:00:00+01:00', 'to': '2024-04-10T00:00:00Z'})
    assert instant.status_code == 200
    assert instant.json()['total'] == 1
    exported = client.get('/api/audit-logs/export', headers=auditor, params=query)
    assert exported.status_code == 200
    assert 'text/csv' in exported.headers['content-type']
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 2 and all(row['userId'] == marker and row['details'] == "'=unsafe" and row['userName'] == "'=formula" for row in rows)
    assert 'passwordHash' not in exported.text and 'password' not in str(result.json())
    for path in ('/api/audit-logs', '/api/audit-logs/export'):
        for params in ({'action': 'invalid'}, {'from': 'bad'}, {'from': '2024-04-10T00:00:00'}, {'from': '2024-05-01', 'to': '2024-04-01'}, {'userId': 'x' * 101}):
            assert client.get(path, headers=auditor, params=params).status_code == 422


def test_direct_admin_services_with_real_mongo(env):
    """Exercise service methods directly and inspect durable state and errors."""
    from fastapi import HTTPException
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository
    from app.admin.schema import UserCreate, UserInput, RoleInput
    from app.admin.service import create_user, update_user, create_role, update_role, get_entity, audit_query, export_audit

    _, sync_db = env
    dbname = sync_db.name

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        try:
            db = mongo[dbname]
            repo = AdminRepository(db)
            actor = await db.users.find_one({'email': 'admin@ketsip.local'})
            body = UserCreate(name='Direct Service', email='direct@example.com', role='Engineer', password='Direct-password-123')
            user = await create_user(repo, actor, body)
            assert (await db.users.find_one({'email': body.email}))['passwordHash'] != body.password
            with pytest.raises(HTTPException) as duplicate:
                await create_user(repo, actor, body)
            assert duplicate.value.status_code == 409
            update = UserInput(name='Direct Updated', email=body.email, role='Auditor')
            changed = await update_user(repo, actor, user['id'], update)
            assert changed['name'] == 'Direct Updated' and changed['role'] == 'Auditor'
            assert (await get_entity(repo, 'users', user['id']))['name'] == 'Direct Updated'
            with pytest.raises(HTTPException) as missing:
                await get_entity(repo, 'users', 'invalid')
            assert missing.value.status_code == 404
            await update_user(repo, actor, user['id'], None)
            assert (await db.users.find_one({'email': body.email}))['status'] == 'Inactive'
            with pytest.raises(HTTPException) as bad_assignment:
                await create_user(repo, actor, UserCreate(name='Invalid', email='invalid@example.com', role='Engineer', password='Direct-password-123', portfolioAccess=['bad']))
            assert bad_assignment.value.status_code == 422
            removed_role = await db.roles.find_one_and_delete({'name': 'Read Only'})
            try:
                created_role = await create_role(repo, actor, RoleInput(name='Read Only', description='Directly created', permissions=['view']))
                assert (await db.roles.find_one({'_id': created_role['_id']}))['description'] == 'Directly created'
            finally:
                await db.roles.delete_one({'name': 'Read Only'})
                await db.roles.insert_one(removed_role)
            role_doc = await db.roles.find_one({'name': 'Engineer'})
            role = RoleInput(name='Engineer', description='Direct service role', permissions=['view'])
            with pytest.raises(HTTPException) as duplicate_role:
                await create_role(repo, actor, role)
            assert duplicate_role.value.status_code == 409
            try:
                await update_role(repo, actor, str(role_doc['_id']), role)
                assert (await db.roles.find_one({'_id': role_doc['_id']}))['description'] == role.description
                with pytest.raises(HTTPException) as rename:
                    await update_role(repo, actor, str(role_doc['_id']), RoleInput(name='Auditor', permissions=['view']))
                assert rename.value.status_code == 409
            finally:
                await update_role(repo, actor, str(role_doc['_id']), RoleInput(**{key: role_doc[key] for key in ('name', 'description', 'permissions')}))
            content = await export_audit(repo, actor, audit_query(str(actor['_id']), 'create', None, None))
            assert 'Direct-password-123' not in content and 'passwordHash' not in content
            assert await db.audit_logs.count_documents({'entityId': user['id'], 'action': 'delete'}) == 1
        finally:
            await mongo.close()
    asyncio.run(exercise())


def test_admin_lock_lease_contention_recovery_and_owner_release(env):
    """A fresh lease excludes contenders; only its owner can release it."""
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository

    _, sync_db = env

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        repo = AdminRepository(mongo[sync_db.name])
        roles = mongo[sync_db.name].roles
        try:
            assert await repo.acquire_admin_lock('first')
            assert not await repo.acquire_admin_lock('second')
            assert not await repo.renew_admin_lock('second')
            assert await repo.renew_admin_lock('first')
            await repo.release_admin_lock('second')
            assert not await repo.acquire_admin_lock('second')
            await roles.update_one({'name': 'Administrator'}, {'$set': {'adminLockExpiresAt': datetime.now(timezone.utc) - timedelta(minutes=1)}})
            assert not await repo.renew_admin_lock('first')
            assert await repo.acquire_admin_lock('second')
            await repo.release_admin_lock('first')
            assert not await repo.acquire_admin_lock('third')
            await repo.release_admin_lock('second')
            assert await repo.acquire_admin_lock('third')
            await repo.release_admin_lock('third')
            # Pre-lease locks have no safe age; never assume they are stale.
            await roles.update_one({'name': 'Administrator'}, {'$set': {'adminLockOwner': 'legacy'}})
            assert not await repo.acquire_admin_lock('third')
        finally:
            await roles.update_one({'name': 'Administrator'}, {'$unset': {'adminLockOwner': '', 'adminLockExpiresAt': ''}})
            await mongo.close()
    asyncio.run(exercise())


def test_update_user_releases_lock_on_real_mongo_error_branches(env):
    """Errors do not strand the lease or mutate the target account."""
    from fastapi import HTTPException
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository
    from app.admin.schema import UserInput
    from app.admin.service import update_user

    _, sync_db = env

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        db = mongo[sync_db.name]
        repo = AdminRepository(db)
        actor = await db.users.find_one({'email': 'admin@ketsip.local'})
        target = await db.users.find_one({'email': 'engineer@ketsip.local'})
        body = UserInput(name=target['name'], email=target['email'], role=target['role'])
        try:
            assert await repo.acquire_admin_lock('contender')
            with pytest.raises(HTTPException) as busy:
                await update_user(repo, actor, str(target['_id']), body)
            assert busy.value.status_code == 409
            await repo.release_admin_lock('contender')
            cases = [
                ('000000000000000000000000', body, 404),
                (str(target['_id']), body.model_copy(update={'email': actor['email']}), 409),
                (str(target['_id']), body.model_copy(update={'portfolioAccess': ['bad']}), 422),
                (str(actor['_id']), None, 409),
                (str(actor['_id']), UserInput(name=actor['name'], email=actor['email'], role='Engineer'), 409),
            ]
            for identifier, update, status in cases:
                with pytest.raises(HTTPException) as error:
                    await update_user(repo, actor, identifier, update)
                assert error.value.status_code == status
                assert 'adminLockOwner' not in await db.roles.find_one({'name': 'Administrator'})
                assert (await db.users.find_one({'_id': target['_id']})) == target
            assert (await db.users.find_one({'_id': actor['_id']}))['role'] == 'Administrator'
        finally:
            await repo.release_admin_lock('contender')
            await mongo.close()
    asyncio.run(exercise())


def test_concurrent_admin_removals_keep_one_active(env):
    """Competing removals cannot both demote the last two administrators."""
    from fastapi import HTTPException
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository
    from app.admin.schema import UserInput
    from app.admin.service import update_user

    _, sync_db = env

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        db = mongo[sync_db.name]
        repo = AdminRepository(db)
        original = await db.users.find_one({'email': 'admin@ketsip.local'})
        second = {**original, 'email': 'concurrent-admin@example.com'}
        second.pop('_id')
        second['_id'] = (await db.users.insert_one(second)).inserted_id
        actor = {'_id': 'independent-operator', 'name': 'Test operator'}
        async def demote(doc):
            try:
                await update_user(repo, actor, str(doc['_id']), UserInput(name=doc['name'], email=doc['email'], role='Engineer'))
                return 200
            except HTTPException as exc:
                return exc.status_code
        try:
            results = await asyncio.gather(demote(original), demote(second))
            assert sorted(results) == [200, 409]
            assert await repo.active_admin_count() == 1
        finally:
            await db.users.replace_one({'_id': original['_id']}, original)
            await db.users.delete_one({'_id': second['_id']})
            await mongo.close()
    asyncio.run(exercise())


@pytest.mark.parametrize('field', ['name', 'email', 'role', 'password'])
@pytest.mark.parametrize('bad', ['missing', None, 123, '', 'long'])
def test_user_create_required_field_validation(env, field, bad):
    """Required fields reject omission, null, wrong types and invalid lengths."""
    client, db = env
    admin = headers(client)
    body = {'name': 'Required Test', 'email': 'required@example.com', 'role': 'Engineer', 'password': 'Strong-password-123'}
    if bad == 'missing':
        del body[field]
    else:
        body[field] = 'x' * 300 if bad == 'long' else bad
    response = client.post('/api/users', headers=admin, json=body)
    assert response.status_code == 422, (field, bad, response.text)
    assert db.users.count_documents({'email': 'required@example.com'}) == 0


@pytest.mark.parametrize('field', ['name', 'email', 'role'])
@pytest.mark.parametrize('bad', ['missing', None, 123, '', 'long'])
def test_user_update_required_field_validation(env, field, bad):
    """Invalid replacement fields leave the existing user unchanged."""
    client, db = env
    admin = headers(client)
    original = db.users.find_one({'email': 'engineer@ketsip.local'})
    body = {'name': original['name'], 'email': original['email'], 'role': original['role']}
    if bad == 'missing':
        del body[field]
    else:
        body[field] = 'x' * 300 if bad == 'long' else bad
    response = client.put('/api/users/' + str(original['_id']), headers=admin, json=body)
    assert response.status_code == 422, (field, bad, response.text)
    assert db.users.find_one({'_id': original['_id']}) == original


@pytest.mark.parametrize('method', ['POST', 'PUT'])
@pytest.mark.parametrize(('field', 'bad'), [
    ('name', 'missing'), ('name', None), ('name', 123), ('name', {}),
    ('name', ''), ('name', 'unknown'),
    ('permissions', 'missing'), ('permissions', None), ('permissions', 123),
    ('permissions', 'view'), ('permissions', {}), ('permissions', [None]),
    ('permissions', [123]), ('permissions', ['view', 'view']),
    ('permissions', ['view', 'create', 'edit', 'delete', 'export', 'view']),
    ('permissions', ['view', 'create', 'edit', 'delete', 'export', 'administer', 'view']),
])
def test_role_invalid_fields_leave_roles_and_audit_unchanged(env, method, field, bad):
    """Reject invalid role fields without writing any role or audit event."""
    client, db = env
    admin = headers(client)
    original = db.roles.find_one({'name': 'Read Only'})
    if method == 'POST':
        db.roles.delete_one({'_id': original['_id']})
    try:
        roles_before = list(db.roles.find().sort('_id', 1))
        audit_before = list(db.audit_logs.find().sort('_id', 1))
        body = {'name': 'Read Only', 'description': 'Should not persist', 'permissions': ['view']}
        if bad == 'missing':
            del body[field]
        else:
            body[field] = bad
        path = '/api/roles' if method == 'POST' else '/api/roles/' + str(original['_id'])
        response = client.request(method, path, headers=admin, json=body)
        assert response.status_code == 422, (method, field, bad, response.text)
        assert any(field in error['loc'] for error in response.json()['detail'])
        assert list(db.roles.find().sort('_id', 1)) == roles_before
        assert list(db.audit_logs.find().sort('_id', 1)) == audit_before
    finally:
        if method == 'POST':
            db.roles.replace_one({'_id': original['_id']}, original, upsert=True)


@pytest.mark.parametrize('method', ['POST', 'PUT'])
@pytest.mark.parametrize('permissions', [[], ['view', 'create', 'edit', 'delete', 'export', 'administer']])
def test_role_permission_list_boundaries_are_accepted(env, method, permissions):
    """Empty and six distinct permissions are valid on create and update."""
    client, db = env
    admin = headers(client)
    original = db.roles.find_one({'name': 'Read Only'})
    if method == 'POST':
        db.roles.delete_one({'_id': original['_id']})
    try:
        body = {'name': 'Read Only', 'description': 'Boundary test', 'permissions': permissions}
        path = '/api/roles' if method == 'POST' else '/api/roles/' + str(original['_id'])
        response = client.request(method, path, headers=admin, json=body)
        assert response.status_code == (201 if method == 'POST' else 200), response.text
        assert response.json()['permissions'] == permissions
        assert db.roles.find_one({'name': 'Read Only'})['permissions'] == permissions
    finally:
        if method == 'POST':
            db.roles.delete_one({'name': 'Read Only'})
        db.roles.replace_one({'_id': original['_id']}, original, upsert=True)


@pytest.mark.parametrize('failure', ['expired', 'lost'])
def test_update_user_rejects_expired_or_lost_lease(env, failure):
    """A failed renewal rejects the write and emits no user audit event.

    A pause after renewal and before the user write can still violate the
    invariant: the lease is neither fenced nor transactional across documents.
    """
    from fastapi import HTTPException
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository
    from app.admin.schema import UserInput
    from app.admin.service import update_user

    _, sync_db = env

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        db = mongo[sync_db.name]

        class LeaseInterruptedRepository(AdminRepository):
            async def renew_admin_lock(self, owner):
                if failure == 'expired':
                    changes = {'adminLockExpiresAt': datetime.now(timezone.utc) - timedelta(minutes=1)}
                else:
                    changes = {'adminLockOwner': 'replacement-owner'}
                result = await self.db.roles.update_one({'name': 'Administrator', 'adminLockOwner': owner}, {'$set': changes})
                assert result.modified_count == 1
                return await super().renew_admin_lock(owner)

        repo = LeaseInterruptedRepository(db)
        actor = await db.users.find_one({'email': 'admin@ketsip.local'})
        target = await db.users.find_one({'email': 'engineer@ketsip.local'})
        query = {'entityId': str(target['_id'])}
        before = await db.audit_logs.count_documents(query)
        try:
            with pytest.raises(HTTPException) as error:
                await update_user(repo, actor, str(target['_id']), UserInput(name='Should not persist', email=target['email'], role=target['role']))
            assert error.value.status_code == 409
            assert error.value.detail == 'Account change lease expired; retry'
            assert await db.users.find_one({'_id': target['_id']}) == target
            assert await db.audit_logs.count_documents(query) == before
            lock = await db.roles.find_one({'name': 'Administrator'})
            if failure == 'lost':
                assert lock['adminLockOwner'] == 'replacement-owner'
            else:
                assert 'adminLockOwner' not in lock
        finally:
            await db.roles.update_one({'name': 'Administrator'}, {'$unset': {'adminLockOwner': '', 'adminLockExpiresAt': ''}})
            await mongo.close()

    asyncio.run(exercise())


@pytest.mark.parametrize('collection', ['users', 'roles'])
def test_update_disappearing_document_returns_not_found(env, collection):
    """A real deletion between read and write yields 404, without an audit."""
    from fastapi import HTTPException
    from pymongo import AsyncMongoClient
    from app.admin.repository import AdminRepository
    from app.admin.schema import RoleInput, UserInput
    from app.admin.service import update_role, update_user

    _, sync_db = env

    async def exercise():
        mongo = AsyncMongoClient(os.environ.get('MONGODB_URI', 'mongodb://127.0.0.1:27017'))
        db = mongo[sync_db.name]

        class DisappearingRepository(AdminRepository):
            async def update(self, name, doc, fields, revoke=False):
                deleted = await self.db[name].delete_one({'_id': doc['_id']})
                assert deleted.deleted_count == 1
                return await super().update(name, doc, fields, revoke=revoke)

        repo = DisappearingRepository(db)
        actor = await db.users.find_one({'email': 'admin@ketsip.local'})
        original = await db[collection].find_one({'email': 'engineer@ketsip.local'} if collection == 'users' else {'name': 'Read Only'})
        identifier = str(original['_id'])
        before = await db.audit_logs.count_documents({'entityId': identifier})
        try:
            with pytest.raises(HTTPException) as error:
                if collection == 'users':
                    await update_user(repo, actor, identifier, UserInput(name=original['name'], email=original['email'], role=original['role']))
                else:
                    await update_role(repo, actor, identifier, RoleInput(**{key: original[key] for key in ('name', 'description', 'permissions')}))
            assert error.value.status_code == 404
            assert await db[collection].find_one({'_id': original['_id']}) is None
            assert await db.audit_logs.count_documents({'entityId': identifier}) == before
            assert 'adminLockOwner' not in await db.roles.find_one({'name': 'Administrator'})
        finally:
            await db[collection].replace_one({'_id': original['_id']}, original, upsert=True)
            await mongo.close()

    asyncio.run(exercise())


def test_audit_export_rejects_more_than_ten_thousand_real_rows(env):
    """An oversized filtered export fails before returning CSV or recording an export."""
    client, db = env
    auditor = headers(client, 'auditor@ketsip.local', 'First-demo-password-123')
    marker = uuid.uuid4().hex
    docs = [{'timestamp': '2024-01-01T00:00:00+00:00', 'userId': marker,
             'userName': 'Test', 'action': 'edit', 'entityType': 'user',
             'entityId': str(i), 'details': 'Test event'} for i in range(10001)]
    try:
        db.audit_logs.insert_many(docs)
        assert db.audit_logs.count_documents({'userId': marker}) == 10001
        exports_before = db.audit_logs.count_documents({'action': 'export', 'entityType': 'audit'})
        response = client.get('/api/audit-logs/export', headers=auditor, params={'userId': marker})
        assert response.status_code == 422
        assert response.json()['detail'] == 'Too many audit events to export; narrow the filters'
        assert db.audit_logs.count_documents({'action': 'export', 'entityType': 'audit'}) == exports_before
    finally:
        db.audit_logs.delete_many({'userId': marker})
