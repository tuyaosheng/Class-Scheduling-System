"""导出全部课表（不再做导出前事后校验，见 cross_grade.py 顶部注释）+
求解阶段的跨年级教师避让集成测试（子项目9）。

各年级独立求解、独立持久化 job——teaching.yaml 在任意时刻只服务"当前
激活"的一个年级（`_run_job` 会拒绝跟 teaching.yaml 里的 grade 对不上的
求解请求），但历史 job 自己持有求解时刻的 Dataset 快照，不受后来
teaching.yaml 被切换成别的年级影响——这正是"求解某年级时能看到其它
年级最近一次求解结果"这套设计能够成立的前提。
"""
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from scheduler.api.app import app
from scheduler.core.importer import ImportResult, write_rules_yaml, write_teaching_yaml
from scheduler.core.models import Dataset, GradeCalendar, Teacher, TeachingTask

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'

CAL_9 = GradeCalendar(
    days=['周一', '周二', '周三', '周四', '周五'], periods_per_day=9, midday_break_after=5,
    clock_times=[('08:00', '08:45'), ('08:55', '09:40'), ('09:50', '10:35'), ('10:45', '11:30'),
                ('11:40', '12:25'), ('14:00', '14:45'), ('14:55', '15:40'), ('15:50', '16:35'),
                ('16:45', '17:30')],
)

# `_run_job` 重建 dataset 时按 grade 从 cfg.calendar_of(grade) 取日历，不看
# 测试里手造的 Dataset.calendar（teaching.yaml 本来就不存日历）——两个年级
# 共用同一套钟点表，这样"跨年级避让是否真的生效"这件事可以直接用 slot
# 索引是否不同来判断，不用跟"作息形状不同"的换算逻辑搅在一起（那部分
# 已经在 test_cross_grade.py 里单独测过）。
_CAL_9_YAML = {
    'days': ['周一', '周二', '周三', '周四', '周五'], 'periods_per_day': 9, 'midday_break_after': 5,
    'clock_times': [list(t) for t in CAL_9.clock_times], 'reserved_slots': [],
}


@pytest.fixture()
def client():
    return TestClient(app)


def _dataset(grade, teacher):
    tasks = [TeachingTask(id=0, grade=grade, class_id=1, course='语文', teacher=teacher, periods=1)]
    return Dataset(grade=grade, classes=[1], teachers={teacher: Teacher(name=teacher)}, tasks=tasks)


@pytest.fixture()
def shared_config_dir(tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    import scheduler.api.ws as ws_module
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(ws_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    for name in ('courses.yaml', 'plans.yaml', 'venues.yaml', 'grades.yaml'):
        src = CONFIG_DIR / name
        if src.exists():
            (tmp_path / name).write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
    (tmp_path / 'calendars.yaml').write_text(
        yaml.safe_dump({'grade_calendars': {'初三': _CAL_9_YAML, '七年级': _CAL_9_YAML}},
                       allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    return tmp_path


def _write_grade_teaching_data(config_dir, grade, teacher):
    dataset = _dataset(grade, teacher)
    result = ImportResult(dataset=dataset, rules=[], warnings=[])
    write_teaching_yaml(result, config_dir / 'teaching.yaml')
    write_rules_yaml(result, config_dir / 'rules.generated.yaml')


def _solve_and_get_job(client, grade):
    resp = client.post('/api/solve', json={'grade': grade, 'count': 1, 'min_diff': 1, 'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    detail = client.get('/api/solve/%s' % job_id).json()
    return job_id, detail


def test_solving_a_second_grade_avoids_the_teachers_already_committed_slot(client, shared_config_dir):
    """核心场景：王老师在初三和七年级都教语文，两个年级共用同一套钟点表
    （slot 索引直接可比）。求解初三先占了某个 slot；求解七年级时应该自动
    避开这个 slot，不需要再靠导出前的事后校验来发现冲突。"""
    _write_grade_teaching_data(shared_config_dir, '初三', '王老师')
    job_a, detail_a = _solve_and_get_job(client, '初三')
    assert detail_a['status'] == 'done'
    slot_a = detail_a['candidates'][0]['placements'][0]['slot']

    _write_grade_teaching_data(shared_config_dir, '七年级', '王老师')
    job_b, detail_b = _solve_and_get_job(client, '七年级')
    assert detail_b['status'] == 'done'
    slot_b = detail_b['candidates'][0]['placements'][0]['slot']

    assert slot_a != slot_b


def test_solving_a_second_grade_with_a_different_teacher_is_unaffected(client, shared_config_dir):
    _write_grade_teaching_data(shared_config_dir, '初三', '张老师')
    _solve_and_get_job(client, '初三')

    _write_grade_teaching_data(shared_config_dir, '七年级', '李老师')
    job_b, detail_b = _solve_and_get_job(client, '七年级')
    assert detail_b['status'] == 'done'


def test_export_all_succeeds_and_returns_a_zip(client, shared_config_dir):
    _write_grade_teaching_data(shared_config_dir, '初三', '张老师')
    job_a, _ = _solve_and_get_job(client, '初三')
    _write_grade_teaching_data(shared_config_dir, '七年级', '李老师')
    job_b, _ = _solve_and_get_job(client, '七年级')

    resp = client.post('/api/export/all', json={
        'selections': [
            {'grade': '初三', 'job_id': job_a, 'candidate_index': 1},
            {'grade': '七年级', 'job_id': job_b, 'candidate_index': 1},
        ],
    })
    assert resp.status_code == 200
    assert resp.headers['content-type'] == 'application/zip'

    import io
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert set(zf.namelist()) == {'初三.xlsx', '七年级.xlsx'}


def test_export_all_rejects_a_job_grade_mismatch(client, shared_config_dir):
    _write_grade_teaching_data(shared_config_dir, '初三', '张老师')
    job_a, _ = _solve_and_get_job(client, '初三')

    resp = client.post('/api/export/all', json={
        'selections': [{'grade': '七年级', 'job_id': job_a, 'candidate_index': 1}],
    })
    assert resp.status_code == 400


def test_export_all_rejects_an_unknown_job_id(client, shared_config_dir):
    resp = client.post('/api/export/all', json={
        'selections': [{'grade': '初三', 'job_id': 'does-not-exist', 'candidate_index': 1}],
    })
    assert resp.status_code == 404
