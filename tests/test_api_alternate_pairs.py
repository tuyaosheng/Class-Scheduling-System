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


def test_get_alternate_pairs_shows_the_imported_art_and_psychology_pair_as_readonly(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/alternate-pairs', params={'grade': '初三'})
    assert resp.status_code == 200
    pairs = resp.json()['pairs']
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair['family'] == '心美'
    assert pair['single_course'] == '美术'
    assert pair['double_course'] == '心理'
    assert pair['editable'] is False   # 来自 rules.generated.yaml（Excel 导入），不能在这里编辑


def test_put_alternate_pairs_adds_a_new_manual_pair(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    # 先给这个年级新增两门尚未配对的课程。
    courses = client.get('/api/config/courses', params={'grade': '初三'}).json()['courses']
    courses.append({'name': '书法', 'family': '书法', 'alternate': None, 'external': False})
    courses.append({'name': '棋艺', 'family': '棋艺', 'alternate': None, 'external': False})
    client.put('/api/config/courses', json={'grade': '初三', 'courses': courses})

    resp = client.put('/api/config/alternate-pairs', json={
        'grade': '初三',
        'pairs': [{'family': '书棋', 'single_course': '书法', 'double_course': '棋艺', 'editable': True}],
    })
    assert resp.status_code == 200
    pairs = resp.json()['pairs']
    manual = [p for p in pairs if p['editable']]
    assert manual == [{'family': '书棋', 'single_course': '书法', 'double_course': '棋艺', 'editable': True}]

    # 课程目录也要同步更新 family/alternate。
    updated = {c['name']: c for c in client.get('/api/config/courses', params={'grade': '初三'}).json()['courses']}
    assert updated['书法']['family'] == '书棋' and updated['书法']['alternate'] == '单周'
    assert updated['棋艺']['family'] == '书棋' and updated['棋艺']['alternate'] == '双周'

    # 排课说明导入生成的美术/心理配对不受影响，仍然只读展示。
    readonly = [p for p in pairs if not p['editable']]
    assert readonly and readonly[0]['single_course'] == '美术'


def test_put_alternate_pairs_rejects_same_course_twice(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/alternate-pairs', json={
        'grade': '初三',
        'pairs': [{'family': 'x', 'single_course': '语文', 'double_course': '语文', 'editable': True}],
    })
    assert resp.status_code == 400


def test_put_alternate_pairs_rejects_unknown_course(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/alternate-pairs', json={
        'grade': '初三',
        'pairs': [{'family': 'x', 'single_course': '语文', 'double_course': '不存在的课', 'editable': True}],
    })
    assert resp.status_code == 400


def test_put_alternate_pairs_rejects_a_course_used_twice_across_pairs(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses', params={'grade': '初三'}).json()['courses']
    courses += [
        {'name': '书法', 'family': '书法', 'alternate': None, 'external': False},
        {'name': '棋艺', 'family': '棋艺', 'alternate': None, 'external': False},
        {'name': '篆刻', 'family': '篆刻', 'alternate': None, 'external': False},
    ]
    client.put('/api/config/courses', json={'grade': '初三', 'courses': courses})

    resp = client.put('/api/config/alternate-pairs', json={
        'grade': '初三',
        'pairs': [
            {'family': 'a', 'single_course': '书法', 'double_course': '棋艺', 'editable': True},
            {'family': 'b', 'single_course': '书法', 'double_course': '篆刻', 'editable': True},
        ],
    })
    assert resp.status_code == 400
    assert '书法' in resp.json()['detail']


def test_put_alternate_pairs_removing_all_clears_manual_pairs_only(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    courses = client.get('/api/config/courses', params={'grade': '初三'}).json()['courses']
    courses += [
        {'name': '书法', 'family': '书法', 'alternate': None, 'external': False},
        {'name': '棋艺', 'family': '棋艺', 'alternate': None, 'external': False},
    ]
    client.put('/api/config/courses', json={'grade': '初三', 'courses': courses})
    client.put('/api/config/alternate-pairs', json={
        'grade': '初三',
        'pairs': [{'family': '书棋', 'single_course': '书法', 'double_course': '棋艺', 'editable': True}],
    })

    resp = client.put('/api/config/alternate-pairs', json={'grade': '初三', 'pairs': []})
    assert resp.status_code == 200
    pairs = resp.json()['pairs']
    assert all(not p['editable'] for p in pairs)   # 手写的配对清空了，导入生成的那份还在
    assert any(p['single_course'] == '美术' for p in pairs)
