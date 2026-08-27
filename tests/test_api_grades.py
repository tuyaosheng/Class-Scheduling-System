import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import app

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'
TEMPLATE = ROOT / '作息表模板.xlsx'


@pytest.fixture()
def client():
    return TestClient(app)


def _use_tmp_config(tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    shutil.copytree(CONFIG_DIR, tmp_path, dirs_exist_ok=True)
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)


# ---------------------------------------------------------------- 年级管理

def test_get_grades_returns_current_list(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/grades')
    assert resp.status_code == 200
    assert resp.json()['grades'] == [{'name': '初三', 'classes': 32}]


def test_put_grades_can_add_a_grade(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    grades = client.get('/api/config/grades').json()['grades']
    grades.append({'name': '初一', 'classes': 8})

    resp = client.put('/api/config/grades', json={'grades': grades})
    assert resp.status_code == 200
    assert resp.json()['grades'] == grades

    reread = client.get('/api/config/grades').json()['grades']
    assert reread == grades


def test_put_grades_rejects_duplicate_names(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/grades', json={'grades': [
        {'name': '初一', 'classes': 8}, {'name': '初一', 'classes': 9},
    ]})
    assert resp.status_code == 400
    assert '初一' in resp.json()['detail']


def test_put_grades_rejects_empty_name(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/grades', json={'grades': [{'name': '  ', 'classes': 8}]})
    assert resp.status_code == 400


def test_put_grades_rejects_non_positive_class_count(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/grades', json={'grades': [{'name': '初一', 'classes': 0}]})
    assert resp.status_code == 400


# ---------------------------------------------------------------- 作息表批量导入

@pytest.mark.skipif(not TEMPLATE.exists(), reason='作息表模板.xlsx 不在仓库里')
def test_parse_calendars_returns_one_entry_per_sheet(client):
    with TEMPLATE.open('rb') as fh:
        resp = client.post('/api/config/calendars/parse',
                           files={'file': ('作息表模板.xlsx', fh,
                                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert resp.status_code == 200
    sheets = {s['sheet_name']: s for s in resp.json()['sheets']}
    assert set(sheets) == {'七年级', '八年级', '九年级'}
    assert sheets['七年级']['periods_per_day'] == 8
    assert sheets['七年级']['midday_break_after'] == 4
    assert sheets['九年级']['periods_per_day'] == 9
    assert sheets['九年级']['midday_break_after'] == 5


def test_get_calendar_returns_404_for_unknown_grade(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/calendars/不存在的年级')
    assert resp.status_code == 404


def test_get_calendar_returns_existing_grade(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.get('/api/config/calendars/初三')
    assert resp.status_code == 200
    body = resp.json()
    assert body['periods_per_day'] == 9
    assert body['midday_break_after'] == 5


def test_put_calendar_writes_a_new_grade_and_preserves_others(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/calendars/初一', json={
        'periods_per_day': 8,
        'midday_break_after': 4,
        'clock_times': [['8:25', '9:05'], ['9:20', '10:00'], ['10:15', '10:55'],
                        ['11:10', '11:50'], ['14:20', '15:00'], ['15:15', '15:55'],
                        ['16:10', '16:50'], ['16:50', '17:30']],
    })
    assert resp.status_code == 200

    reread = client.get('/api/config/calendars/初一').json()
    assert reread['periods_per_day'] == 8
    assert reread['midday_break_after'] == 4

    # 初三原有的日历没被这次写入影响。
    still_there = client.get('/api/config/calendars/初三').json()
    assert still_there['periods_per_day'] == 9
