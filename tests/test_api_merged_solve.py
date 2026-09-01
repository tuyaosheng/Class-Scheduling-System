"""M7 合排 API：POST /api/solve/merged。

各年级复用"该年级最近一次求解"留下的 Dataset/规则快照，联合求解后按
年级各自存成一条普通 SolveJob——直接复用现有历史列表/导出基础设施。
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
    result = ImportResult(dataset=_dataset(grade, teacher), rules=[], warnings=[])
    write_teaching_yaml(result, config_dir / 'teaching.yaml')
    write_rules_yaml(result, config_dir / 'rules.generated.yaml')


def _solve_once(client, grade):
    resp = client.post('/api/solve', json={'grade': grade, 'count': 1, 'min_diff': 1, 'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    return job_id


def test_merged_solve_requires_at_least_two_grades(client, shared_config_dir):
    _write_grade_teaching_data(shared_config_dir, '初三', '张老师')
    _solve_once(client, '初三')

    resp = client.post('/api/solve/merged', json={'grades': ['初三'], 'max_seconds': 10})
    assert resp.status_code == 400
    assert '至少' in resp.json()['detail']


def test_merged_solve_rejects_a_grade_never_solved_before(client, shared_config_dir):
    resp = client.post('/api/solve/merged', json={'grades': ['初三', '七年级'], 'max_seconds': 10})
    assert resp.status_code == 400
    assert '还没有求解过' in resp.json()['detail']


def test_merged_solve_succeeds_and_creates_a_job_per_grade(client, shared_config_dir):
    _write_grade_teaching_data(shared_config_dir, '初三', '张老师')
    _solve_once(client, '初三')
    _write_grade_teaching_data(shared_config_dir, '七年级', '李老师')
    _solve_once(client, '七年级')

    resp = client.post('/api/solve/merged', json={'grades': ['初三', '七年级'], 'max_seconds': 10})
    assert resp.status_code == 200
    results = {r['grade']: r for r in resp.json()['results']}
    assert results['初三']['status'] in ('OPTIMAL', 'FEASIBLE')
    assert results['七年级']['status'] in ('OPTIMAL', 'FEASIBLE')

    # 每个年级都生成了一条新的、可以直接用现有历史列表/导出查看的 SolveJob。
    for grade, r in results.items():
        job_detail = client.get('/api/solve/%s' % r['job_id']).json()
        assert job_detail['grade'] == grade
        assert len(job_detail['candidates']) == 1


def test_merged_solve_avoids_cross_grade_teacher_conflicts_even_when_the_solo_solves_did_not(
        client, shared_config_dir):
    """王老师在两个年级都独立求解过——独立求解互不知道对方，可能（也可能
    巧合没有）撞车；合排求解出来的结果必须真的没有跨年级冲突，不能只是
    延续两次独立求解偶然凑巧的结果。"""
    _write_grade_teaching_data(shared_config_dir, '初三', '王老师')
    _solve_once(client, '初三')
    _write_grade_teaching_data(shared_config_dir, '七年级', '王老师')
    _solve_once(client, '七年级')

    resp = client.post('/api/solve/merged', json={'grades': ['初三', '七年级'], 'max_seconds': 10})
    assert resp.status_code == 200
    results = {r['grade']: r for r in resp.json()['results']}
    assert results['初三']['status'] in ('OPTIMAL', 'FEASIBLE')
    assert results['七年级']['status'] in ('OPTIMAL', 'FEASIBLE')

    slot_a = client.get('/api/solve/%s' % results['初三']['job_id']).json()['candidates'][0]['placements'][0]['slot']
    slot_b = client.get('/api/solve/%s' % results['七年级']['job_id']).json()['candidates'][0]['placements'][0]['slot']
    # 两个年级用的是同一套日历（本测试特意让钟点表一致），slot 相同就意味着
    # 真实撞车——合排必须把王老师排到不同的 slot。
    assert slot_a != slot_b
