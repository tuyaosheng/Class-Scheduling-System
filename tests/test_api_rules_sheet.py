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


def _make_rule_sheet(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['占位表头行，程序从第3行起读'])
    ws.append(['姓名', '任教年级', '学科', '职务', '固定节次', '不能排课节次', '排课要求', '备注'])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_download_template_returns_an_xlsx_file(client):
    resp = client.get('/api/config/rules-sheet/template')
    assert resp.status_code == 200
    assert resp.headers['content-type'] == \
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def test_parse_returns_rules_and_teacher_facts_without_writing_anything(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    rules_before = (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8')
    teaching_before = (tmp_path / 'teaching.yaml').read_text(encoding='utf-8')

    file_path = _make_rule_sheet(tmp_path / '排课说明.xlsx',
                                 [['测试老师', '初三', '语文', '', '', '周二上午不排课', '', '']])
    with file_path.open('rb') as fh:
        resp = client.post('/api/config/rules-sheet/parse', params={'grade': '初三'},
                           files={'file': ('排课说明.xlsx', fh,
                                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert resp.status_code == 200
    body = resp.json()
    assert any(r['type'] == 'forbid_slots' and r['scope'].get('teacher') == '测试老师' for r in body['rules'])
    assert any(f['name'] == '测试老师' for f in body['teacher_facts'])
    assert body['ai_reviewed'] is False

    assert (tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8') == rules_before
    assert (tmp_path / 'teaching.yaml').read_text(encoding='utf-8') == teaching_before


def test_put_writes_rules_generated_yaml_scoped_to_the_grade(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    resp = client.put('/api/config/rules-sheet', json={
        'grade': '初三',
        'rules': [{'type': 'forbid_slots', 'scope': {'grade': '初三', 'teacher': '测试老师'},
                   'params': {'slots': [[1, 1]]}, 'mode': 'hard'}],
        'teacher_facts': [{'name': '测试老师', 'duties': [], 'forbidden': [[1, 1]]}],
    })
    assert resp.status_code == 200
    assert resp.json() == {'ok': True, 'rules_written': 1, 'teachers_updated': 1}

    data = yaml.safe_load((tmp_path / 'rules.generated.yaml').read_text(encoding='utf-8'))
    assert any(r['scope'].get('teacher') == '测试老师' for r in data['rules'])


def test_put_preserves_teachers_not_mentioned_in_this_batch(client, tmp_path, monkeypatch):
    """真实场景：李琼在真实 teaching.yaml 里已有 duties/forbidden，这次排课规则
    导入只提到别的教师时，李琼的记录不能被清空。"""
    _use_tmp_config(tmp_path, monkeypatch)
    before = yaml.safe_load((tmp_path / 'teaching.yaml').read_text(encoding='utf-8'))
    li_qiong_before = next(t for t in before['teachers'] if t['name'] == '李琼')

    resp = client.put('/api/config/rules-sheet', json={
        'grade': '初三',
        'rules': [],
        'teacher_facts': [{'name': '徐仪涵', 'duties': [], 'forbidden': [[0, 1]]}],
    })
    assert resp.status_code == 200

    after = yaml.safe_load((tmp_path / 'teaching.yaml').read_text(encoding='utf-8'))
    li_qiong_after = next(t for t in after['teachers'] if t['name'] == '李琼')
    assert li_qiong_after == li_qiong_before


def test_put_rejects_when_teaching_yaml_does_not_exist_yet(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    (tmp_path / 'teaching.yaml').unlink()
    resp = client.put('/api/config/rules-sheet', json={
        'grade': '初三', 'rules': [], 'teacher_facts': [{'name': 'X', 'duties': [], 'forbidden': []}],
    })
    assert resp.status_code == 400
    assert '任课表' in resp.json()['detail']


def test_parse_rejects_a_course_not_in_the_grade_catalog(client, tmp_path, monkeypatch):
    _use_tmp_config(tmp_path, monkeypatch)
    file_path = _make_rule_sheet(tmp_path / '排课说明.xlsx',
                                 [['测试老师', '初三', '不存在的课', '', '', '', '', '']])
    with file_path.open('rb') as fh:
        resp = client.post('/api/config/rules-sheet/parse', params={'grade': '初三'},
                           files={'file': ('排课说明.xlsx', fh,
                                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert resp.status_code == 400
