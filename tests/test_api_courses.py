import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import app

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'


@pytest.fixture()
def client():
    return TestClient(app)


def _use_tmp_config(tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    shutil.copytree(CONFIG_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)


def test_get_courses_returns_current_catalog(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/courses')
    assert resp.status_code == 200
    courses = resp.json()['courses']
    names = {c['name'] for c in courses}
    assert '语文' in names and '体比' in names
    tibi = next(c for c in courses if c['name'] == '体比')
    assert tibi['external'] is True
    assert tibi['venue'] == '操场'


def test_put_courses_round_trips(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    get_resp = client.get('/api/config/courses')
    courses = get_resp.json()['courses']

    put_resp = client.put('/api/config/courses', json={'courses': courses})
    assert put_resp.status_code == 200

    reread = client.get('/api/config/courses')
    assert reread.json()['courses'] == courses


def test_put_courses_can_add_a_placeholder_course(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses').json()['courses']
    courses.append({'name': '眼操', 'family': '眼操', 'external': True})

    resp = client.put('/api/config/courses', json={'courses': courses})
    assert resp.status_code == 200

    reread = client.get('/api/config/courses').json()['courses']
    added = next(c for c in reread if c['name'] == '眼操')
    assert added['external'] is True


def test_put_courses_rejects_duplicate_names(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses').json()['courses']
    courses.append({'name': '语文', 'family': '语文'})

    resp = client.put('/api/config/courses', json={'courses': courses})
    assert resp.status_code == 400
    assert '语文' in resp.json()['detail']


def test_put_courses_rejects_deleting_a_course_still_referenced_by_a_plan(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses').json()['courses']
    # 语文在 plans.yaml 的初三计划里被引用，删掉它必须失败
    remaining = [c for c in courses if c['name'] != '语文']

    resp = client.put('/api/config/courses', json={'courses': remaining})
    assert resp.status_code == 400


def test_put_courses_auto_creates_new_venue(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses').json()['courses']
    courses.append({'name': '新课', 'family': '新课', 'venue': '新场地'})

    resp = client.put('/api/config/courses', json={'courses': courses})
    assert resp.status_code == 200

    venues_raw = (tmp_path / 'venues.yaml').read_text(encoding='utf-8')
    assert '新场地' in venues_raw
