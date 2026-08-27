import shutil
from pathlib import Path

import openpyxl
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


def _make_teaching_table_file(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['初三'])
    ws.append(['班别', '语文', '数学'])
    ws.append([1, '李琼', '徐仪涵'])
    ws.append([2, '郑艳秀', '徐仪涵'])
    wb.save(path)
    return path


def test_get_teaching_table_returns_empty_entries_before_any_import(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    (tmp_path / 'teaching.yaml').unlink(missing_ok=True)
    resp = client.get('/api/config/teaching-table', params={'grade': '初三'})
    assert resp.status_code == 200
    body = resp.json()
    assert body['classes'] == list(range(1, 33))   # grades.yaml 里初三=32个班
    assert '语文' in body['courses']
    assert body['entries'] == []


def test_parse_previews_without_writing_teaching_yaml(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    (tmp_path / 'teaching.yaml').unlink(missing_ok=True)
    file_path = _make_teaching_table_file(tmp_path / '任课表.xlsx')

    with file_path.open('rb') as fh:
        resp = client.post('/api/config/teaching-table/parse', params={'grade': '初三'},
                           files={'file': ('任课表.xlsx', fh,
                                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert resp.status_code == 200
    entries = {(e['class_id'], e['course']): e['teacher'] for e in resp.json()['entries']}
    assert entries[(1, '语文')] == '李琼'
    assert entries[(1, '数学')] == '徐仪涵'

    assert not (tmp_path / 'teaching.yaml').exists()


def test_put_teaching_table_writes_teaching_yaml_with_plan_derived_periods(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/teaching-table', json={
        'grade': '初三',
        'entries': [
            {'class_id': 1, 'course': '语文', 'teacher': '李琼'},
            {'class_id': 1, 'course': '数学', 'teacher': '徐仪涵'},
        ],
    })
    assert resp.status_code == 200

    written = yaml.safe_load((tmp_path / 'teaching.yaml').read_text(encoding='utf-8'))
    chinese = next(t for t in written['tasks'] if t['course'] == '语文')
    assert chinese['periods'] == 7   # 来自 plans.yaml 的初三课程计划，不是 Excel 里的数字

    reread = client.get('/api/config/teaching-table', params={'grade': '初三'}).json()
    assert {(e['class_id'], e['course']): e['teacher'] for e in reread['entries']} == {
        (1, '语文'): '李琼', (1, '数学'): '徐仪涵',
    }


def test_put_teaching_table_does_not_touch_rules_generated_yaml(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    before = (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8')

    client.put('/api/config/teaching-table', json={
        'grade': '初三',
        'entries': [{'class_id': 1, 'course': '语文', 'teacher': '李琼'}],
    })

    after = (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8')
    assert before == after


def test_put_teaching_table_preserves_an_existing_teachers_duties_and_forbidden(client, tmp_path, monkeypatch):
    """真实发生过的数据丢失（浏览器实测中招过一次）：李琼在真实 teaching.yaml 里
    是班主任、有禁排节次——只改一个别的格子并保存，这些信息不能被清空。"""
    _use_tmp_config(tmp_path, monkeypatch)
    before = yaml.safe_load((tmp_path / 'teaching.yaml').read_text(encoding='utf-8'))
    li_qiong_before = next(t for t in before['teachers'] if t['name'] == '李琼')
    assert li_qiong_before['duties'] == ['班主任']

    resp = client.put('/api/config/teaching-table', json={
        'grade': '初三',
        'entries': [{'class_id': 1, 'course': '语文', 'teacher': '李琼'},
                    {'class_id': 2, 'course': '数学', 'teacher': '徐仪涵'}],
    })
    assert resp.status_code == 200

    after = yaml.safe_load((tmp_path / 'teaching.yaml').read_text(encoding='utf-8'))
    li_qiong_after = next(t for t in after['teachers'] if t['name'] == '李琼')
    assert li_qiong_after['duties'] == ['班主任']
    assert li_qiong_after['forbidden'] == li_qiong_before['forbidden']
    assert li_qiong_after['forbidden']   # 确认真的有内容可保留，不是空列表对空列表的假阳性


def test_put_teaching_table_rejects_a_course_without_a_plan_entry(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/teaching-table', json={
        'grade': '初三',
        'entries': [{'class_id': 1, 'course': '综实1', 'teacher': '陈芬'}],
    })
    # 综实1 在 plans.yaml 里有周课时（1），应该成功；换一门真的没配的课再验证失败路径
    assert resp.status_code == 200

    resp2 = client.put('/api/config/teaching-table', json={
        'grade': '初一',   # 初一课程计划是空的（plans.yaml: 初一: {}）
        'entries': [{'class_id': 1, 'course': '语文', 'teacher': '某老师'}],
    })
    assert resp2.status_code == 400
