import shutil
from pathlib import Path

import pytest
import yaml
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


def test_get_rules_returns_hand_written_rules_only(client, tmp_path, monkeypatch):
    """rules.yaml 手写的 teacher_max_run 应该出现，但 rules.generated.yaml
    里那 121 位教师的 forbid_slots 不该混进来——两个文件的编辑权限不同。"""
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/rules')
    assert resp.status_code == 200
    body = resp.json()
    types = [r['type'] for r in body['rules']]
    assert types == ['teacher_max_run']
    assert 'daily_min' in body['rule_types']
    assert 'forbid_slots' in body['rule_types']


def test_put_rules_round_trips(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    rules = client.get('/api/config/rules').json()['rules']

    resp = client.put('/api/config/rules', json={'rules': rules})
    assert resp.status_code == 200

    reread = client.get('/api/config/rules').json()['rules']
    assert reread == rules


def test_put_rules_can_add_a_soft_rule_with_weight(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    rules = client.get('/api/config/rules').json()['rules']
    rules.append({
        'type': 'daily_max', 'scope': {'grade': '初三', 'family': '物理'},
        'params': {'n': 1}, 'mode': 'soft', 'enabled': True, 'weight': 3,
    })

    resp = client.put('/api/config/rules', json={'rules': rules})
    assert resp.status_code == 200

    reread = client.get('/api/config/rules').json()['rules']
    added = next(r for r in reread if r['type'] == 'daily_max')
    assert added['weight'] == 3
    assert added['scope'] == {'grade': '初三', 'family': '物理'}


def test_put_rules_rejects_unknown_type(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    rules = client.get('/api/config/rules').json()['rules']
    rules.append({'type': 'fly_to_moon', 'scope': {}, 'params': {}, 'mode': 'hard',
                  'enabled': True, 'weight': 0})

    resp = client.put('/api/config/rules', json={'rules': rules})
    assert resp.status_code == 400
    assert 'fly_to_moon' in resp.json()['detail']


def test_put_rules_rejects_unknown_scope_dimension(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    rules = client.get('/api/config/rules').json()['rules']
    rules.append({'type': 'daily_min', 'scope': {'planet': '地球'}, 'params': {'n': 1},
                  'mode': 'hard', 'enabled': True, 'weight': 0})

    resp = client.put('/api/config/rules', json={'rules': rules})
    assert resp.status_code == 400
    assert 'planet' in resp.json()['detail']


def test_put_rules_does_not_touch_the_generated_file(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    before = (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8')

    rules = client.get('/api/config/rules').json()['rules']
    rules.append({'type': 'daily_min', 'scope': {'grade': '初三'}, 'params': {'n': 1},
                  'mode': 'hard', 'enabled': True, 'weight': 0})
    client.put('/api/config/rules', json={'rules': rules})

    after = (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8')
    assert before == after
