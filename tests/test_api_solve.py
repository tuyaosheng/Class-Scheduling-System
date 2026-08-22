from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import app
from scheduler.core.config import load_config
from scheduler.core.importer import write_rules_yaml, write_teaching_yaml
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.importer import ImportResult

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'


@pytest.fixture()
def client():
    return TestClient(app)


def _tiny_feasible_dataset():
    """给一个班排 3 门课、每门 1 节，足够在 45 格里求出多个不同排法。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='张老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=1, course='数学', teacher='李老师', periods=1),
        TeachingTask(id=2, grade='初三', class_id=1, course='英语', teacher='王老师', periods=1),
    ]
    return Dataset(grade='初三', classes=[1],
                   teachers={t.teacher: Teacher(name=t.teacher) for t in tasks}, tasks=tasks)


@pytest.fixture()
def tiny_config(tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    import scheduler.api.ws as ws_module
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(ws_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    cfg = load_config(CONFIG_DIR)
    dataset = _tiny_feasible_dataset()
    result = ImportResult(dataset=dataset, rules=[], warnings=[])
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_teaching_yaml(result, tmp_path / 'teaching.yaml')
    write_rules_yaml(result, tmp_path / 'rules.generated.yaml')
    for name in ('courses.yaml', 'plans.yaml', 'venues.yaml'):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text(encoding='utf-8'),
                                     encoding='utf-8')
    return tmp_path


def test_solve_then_websocket_receives_candidates_and_done(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 2, 'min_diff': 1,
                                           'max_seconds': 10})
    assert resp.status_code == 200
    job_id = resp.json()['job_id']

    events = []
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            events.append(msg)
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break

    types = [e['type'] for e in events]
    assert 'solving' in types
    candidates = [e for e in events if e['type'] == 'candidate']
    assert len(candidates) >= 1
    assert candidates[0]['status'] == 'OPTIMAL'
    assert candidates[0]['violations'] == []
    assert types[-1] == 'done'


def test_solve_job_status_reachable_via_polling(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    status_resp = client.get('/api/solve/%s' % job_id)
    assert status_resp.status_code == 200
    assert status_resp.json()['status'] == 'done'


def test_export_returns_xlsx_file(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    export_resp = client.get('/api/export/%s/1' % job_id)
    assert export_resp.status_code == 200
    assert export_resp.headers['content-type'].startswith(
        'application/vnd.openxmlformats')
