"""Verify dependency-free liveness for deployment probes."""
from fastapi.testclient import TestClient
from app.main import app


def test_health_without_database_lifespan():
    """Return a stable health response without starting persistence."""
    client = TestClient(app)
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
