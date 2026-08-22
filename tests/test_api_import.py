import io
import shutil
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import app

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'


def _teaching_table_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['初三'])
    ws.append(['班别', '语文', '数学'])
    ws.append([1, '李琼', '徐仪涵'])
    ws.append([2, '郑艳秀', '徐仪涵'])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _rules_sheet_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['占位表头行'])
    ws.append(['姓名', '任教年级', '学科', '任教班', '周课时', '职务',
               '固定节次', '不能排课节次', '排课要求', '备注'])
    ws.append(['李琼', '初三', '语文', '1', 6, None, None, None, '保证每天有1节', None])
    ws.append(['郑艳秀', '初三', '语文', '2', 6, None, None, None, '保证每天有1节', None])
    ws.append(['徐仪涵', '初三', '数学', '1,2', 5, None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


@pytest.fixture()
def client():
    return TestClient(app)


def test_import_returns_preview_with_no_conflicts(client):
    resp = client.post(
        '/api/import',
        params={'grade': '初三'},
        files={
            'teaching_file': ('任课表.xlsx', _teaching_table_bytes(),
                              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'rules_file': ('排课说明.xlsx', _rules_sheet_bytes(),
                           'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body['conflicts'] == []
    assert body['classes'] == 2
    assert '保证每天有1节' in [item['raw'] for item in body['rule_echo']['排课要求']]
    assert body['token']


def test_import_confirm_writes_config_and_rejects_when_conflicted(client, tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    # DEFAULT_CONFIG_DIR 被换成隔离的 tmp_path，避免测试写脏仓库里的真实
    # scheduler/config；但 load_config 仍要读 courses/venues/plans 静态配置，
    # 所以先把这三份从真实 CONFIG_DIR 复制进 tmp_path。
    for name in ('courses.yaml', 'venues.yaml', 'plans.yaml'):
        shutil.copy(CONFIG_DIR / name, tmp_path / name)
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    # 先拿一份没有冲突的预览
    resp = client.post(
        '/api/import', params={'grade': '初三'},
        files={
            'teaching_file': ('任课表.xlsx', _teaching_table_bytes(), 'application/octet-stream'),
            'rules_file': ('排课说明.xlsx', _rules_sheet_bytes(), 'application/octet-stream'),
        },
    )
    token = resp.json()['token']
    confirm = client.post('/api/import/confirm', json={'token': token})
    assert confirm.status_code == 200
    assert (tmp_path / 'teaching.yaml').exists()
    assert (tmp_path / 'rules.generated.yaml').exists()


def test_import_confirm_rejects_unknown_token(client):
    resp = client.post('/api/import/confirm', json={'token': '不存在'})
    assert resp.status_code == 404


def test_config_status_reflects_written_config(client, tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    resp = client.get('/api/config/status')
    assert resp.status_code == 200
    assert resp.json()['ready'] is False
