from fastapi.testclient import TestClient

from scheduler.api.app import app


def test_app_has_cors_configured_for_vite_dev_server():
    client = TestClient(app)
    resp = client.options(
        '/api/config/status',
        headers={
            'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'GET',
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get('access-control-allow-origin') == 'http://localhost:5173'


def test_config_status_endpoint_reachable_through_full_app():
    client = TestClient(app)
    resp = client.get('/api/config/status')
    assert resp.status_code == 200
    assert 'ready' in resp.json()
