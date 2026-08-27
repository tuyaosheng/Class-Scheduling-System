from scheduler.api import sessions
from scheduler.core.importer import ImportResult
from scheduler.core.models import Dataset, Teacher, TeachingTask


def _fake_result():
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='张老师', periods=1)
    dataset = Dataset(grade='初三', classes=[1], teachers={'张老师': Teacher(name='张老师')},
                      tasks=[task])
    return ImportResult(dataset=dataset, rules=[], warnings=[])


def test_save_and_get_import_roundtrip():
    result = _fake_result()
    token = sessions.save_import(result, grade='初三')
    session = sessions.get_import(token)
    assert session is not None
    assert session.result.dataset.grade == '初三'
    assert session.grade == '初三'


def test_get_import_returns_none_for_unknown_token():
    assert sessions.get_import('不存在的token') is None


def test_list_imports_summarizes_by_created_time_desc():
    token1 = sessions.save_import(_fake_result(), grade='初三')
    token2 = sessions.save_import(_fake_result(), grade='初三')
    tokens = [row['token'] for row in sessions.list_imports()]
    assert tokens == [token2, token1]


def test_delete_import_removes_it():
    token = sessions.save_import(_fake_result(), grade='初三')
    sessions.delete_import(token)
    assert sessions.get_import(token) is None


def test_clear_imports_removes_all():
    sessions.save_import(_fake_result(), grade='初三')
    sessions.save_import(_fake_result(), grade='初三')
    sessions.clear_imports()
    assert sessions.list_imports() == []


def test_create_job_has_unique_id_and_pending_status():
    job1 = sessions.create_job(grade='初三')
    job2 = sessions.create_job(grade='初三')
    assert job1.job_id != job2.job_id
    assert job1.status == 'pending'


def test_get_job_reloads_persisted_fields():
    job = sessions.create_job(grade='初三')
    job.status = 'solving'
    sessions.save_job(job)

    reloaded = sessions.get_job(job.job_id)
    assert reloaded is not None
    assert reloaded.job_id == job.job_id
    assert reloaded.status == 'solving'
    assert reloaded.grade == '初三'


def test_get_job_returns_none_for_unknown_id():
    assert sessions.get_job('不存在的job') is None


def test_get_job_migrates_pre_2026_08_28_flat_courses_shape():
    """旧版本存的 cfg.courses 是全局扁平字典（没有按年级分组）——课程目录
    改成按年级分组之后，读旧数据不该直接报 pydantic ValidationError/500，
    得按 job 自己的 grade 包一层，等价于「旧数据本来就只有这一个年级」。"""
    from scheduler.core import session_store

    job = sessions.create_job(grade='初三')
    old_shape_cfg = {
        'courses': {'语文': {'name': '语文', 'family': '语文', 'venue': None,
                            'alternate': None, 'external': False}},
        'plans': {}, 'venues': {}, 'reserved_slots': {}, 'calendars': {}, 'grades': [],
    }
    session_store.update_job(job.job_id, 'pending', {
        'issues': [], 'conflict': None, 'solutions': [], 'violations': [],
        'dataset': None, 'cfg': old_shape_cfg, 'rules': [], 'ai_findings': {},
    })

    reloaded = sessions.get_job(job.job_id)
    assert reloaded is not None
    assert reloaded.cfg.courses_of('初三')['语文'].family == '语文'


def test_list_jobs_reports_candidate_count():
    from scheduler.core.solver import Solution

    job = sessions.create_job(grade='初三')
    job.solutions = [Solution(status='OPTIMAL', wall_time=0.1, placements=[])]
    sessions.save_job(job)

    rows = sessions.list_jobs()
    row = next(r for r in rows if r['job_id'] == job.job_id)
    assert row['candidate_count'] == 1
    assert row['grade'] == '初三'


def test_delete_job_removes_it():
    job = sessions.create_job(grade='初三')
    sessions.delete_job(job.job_id)
    assert sessions.get_job(job.job_id) is None


def test_clear_jobs_removes_all():
    sessions.create_job(grade='初三')
    sessions.create_job(grade='初三')
    sessions.clear_jobs()
    assert sessions.list_jobs() == []
