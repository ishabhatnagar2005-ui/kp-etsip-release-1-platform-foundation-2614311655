"""Persist administration records and audit queries with async PyMongo."""
from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from app.auth.repository import now


def identifier(value: str) -> ObjectId | None:
    """Convert a valid external identifier to Mongo's key type."""
    return ObjectId(value) if ObjectId.is_valid(value) else None


def project(doc: dict) -> dict:
    """Convert a Mongo document into an API-safe identifier shape."""
    return {**doc, 'id': str(doc['_id'])}


class AdminRepository:
    """Read and write users, fixed roles, and audit events."""
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def page(self, collection: str, query: dict, limit: int, offset: int) -> dict:
        """Return a deterministic bounded page and its total."""
        coll = self.db[collection]
        order = [('timestamp', -1), ('_id', -1)] if collection == 'audit_logs' else [('name', 1), ('_id', 1)]
        items = await coll.find(query).sort(order).skip(offset).limit(limit).to_list(length=limit)
        return {'items': [project(item) for item in items], 'total': await coll.count_documents(query), 'limit': limit, 'offset': offset}

    async def get(self, collection: str, value: str) -> dict | None:
        """Find an entity by its external identifier."""
        oid = identifier(value)
        return await self.db[collection].find_one({'_id': oid}) if oid else None

    async def insert(self, collection: str, fields: dict) -> dict:
        """Insert a timestamped document and return its stored form."""
        stamp = now()
        doc = {**fields, 'createdAt': stamp, 'updatedAt': stamp}
        await self.db[collection].insert_one(doc)
        return doc

    async def update(self, collection: str, doc: dict, fields: dict, revoke: bool = False) -> dict | None:
        """Update a document and optionally invalidate its sessions."""
        changes = {'$set': {**fields, 'updatedAt': now()}}
        if revoke:
            changes['$inc'] = {'tokenVersion': 1}
        return await self.db[collection].find_one_and_update({'_id': doc['_id']}, changes, return_document=ReturnDocument.AFTER)

    async def portfolios_exist(self, ids: list[str]) -> bool:
        """Confirm each assigned portfolio exists."""
        if any(identifier(item) is None for item in ids):
            return False
        return await self.db.portfolios.count_documents({'_id': {'$in': [ObjectId(item) for item in ids]}}) == len(ids)

    async def active_admin_count(self) -> int:
        """Count active administrators before changing their accounts."""
        return await self.db.users.count_documents({'role': 'Administrator', 'status': 'Active'})

    async def acquire_admin_lock(self, owner: str) -> bool:
        """Acquire a fail-closed database-wide lock for admin account changes."""
        result = await self.db.roles.find_one_and_update(
            {'name': 'Administrator', 'adminLockOwner': {'$exists': False}},
            {'$set': {'adminLockOwner': owner}},
            return_document=ReturnDocument.AFTER,
        )
        return result is not None

    async def release_admin_lock(self, owner: str) -> None:
        """Release only the lock held by this operation."""
        await self.db.roles.update_one({'name': 'Administrator', 'adminLockOwner': owner}, {'$unset': {'adminLockOwner': ''}})

    async def audit(self, actor: dict, action: str, entity: str, entity_id: str | None, details: str) -> None:
        """Append an event containing no request payload or credentials."""
        stamp = now()
        await self.db.audit_logs.insert_one({'timestamp': stamp, 'createdAt': stamp, 'updatedAt': stamp, 'userId': str(actor['_id']), 'userName': actor['name'], 'action': action, 'entityType': entity, 'entityId': entity_id, 'details': details})
