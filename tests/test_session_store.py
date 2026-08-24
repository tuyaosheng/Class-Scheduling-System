from scheduler.core import session_store


def test_import_round_trip():
    session_store.save_import('tok1', '初三', {'foo': 'bar'})
    assert session_store.load_import('tok1') == {'foo': 'bar'}


def test_load_import_returns_none_for_unknown_token():
    assert session_store.load_import('不存在') is None


def test_list_imports_sorted_newest_first():
    session_store.save_import('tok1', '初三', {})
    session_store.save_import('tok2', '初三', {})
    tokens = [row['token'] for row in session_store.list_imports()]
    assert tokens == ['tok2', 'tok1']


def test_delete_import():
    session_store.save_import('tok1', '初三', {})
    session_store.delete_import('tok1')
    assert session_store.load_import('tok1') is None


def test_clear_imports():
    session_store.save_import('tok1', '初三', {})
    session_store.save_import('tok2', '初三', {})
    session_store.clear_imports()
    assert session_store.list_imports() == []


def test_job_create_then_update_preserves_created_at():
    session_store.create_job('job1', '初三')
    created_at = session_store.load_job('job1')['created_at']

    session_store.update_job('job1', 'solving', {'solutions': []})
    reloaded = session_store.load_job('job1')

    assert reloaded['status'] == 'solving'
    assert reloaded['created_at'] == created_at


def test_load_job_returns_none_for_unknown_id():
    assert session_store.load_job('不存在') is None


def test_list_jobs_reports_candidate_count_from_data():
    session_store.create_job('job1', '初三')
    session_store.update_job('job1', 'done', {'solutions': [{}, {}]})
    row = next(r for r in session_store.list_jobs() if r['job_id'] == 'job1')
    assert row['candidate_count'] == 2


def test_list_jobs_sorted_newest_first():
    session_store.create_job('job1', '初三')
    session_store.create_job('job2', '初三')
    ids = [row['job_id'] for row in session_store.list_jobs()]
    assert ids == ['job2', 'job1']


def test_delete_job():
    session_store.create_job('job1', '初三')
    session_store.delete_job('job1')
    assert session_store.load_job('job1') is None


def test_clear_jobs():
    session_store.create_job('job1', '初三')
    session_store.create_job('job2', '初三')
    session_store.clear_jobs()
    assert session_store.list_jobs() == []
