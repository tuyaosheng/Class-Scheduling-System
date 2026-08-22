from scheduler.api import sessions


def test_save_and_get_import_roundtrip():
    fake_result = object()   # 会话层不关心具体类型，只负责存取
    token = sessions.save_import(fake_result, grade='初三')
    session = sessions.get_import(token)
    assert session is not None
    assert session.result is fake_result
    assert session.grade == '初三'


def test_get_import_returns_none_for_unknown_token():
    assert sessions.get_import('不存在的token') is None


def test_create_job_has_unique_id_and_pending_status():
    job1 = sessions.create_job()
    job2 = sessions.create_job()
    assert job1.job_id != job2.job_id
    assert job1.status == 'pending'
    assert sessions.get_job(job1.job_id) is job1


def test_get_job_returns_none_for_unknown_id():
    assert sessions.get_job('不存在的job') is None
