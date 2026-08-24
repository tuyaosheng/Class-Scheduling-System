import queue as queue_mod
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scheduler.api.app import app
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel, write_rules_yaml, write_teaching_yaml
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.importer import ImportResult
from scheduler.core.rules import load_rules

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'
EXCEL = ROOT / '任课与排课说明.xlsx'


@pytest.fixture()
def client():
    return TestClient(app)


def _tiny_feasible_dataset():
    """给一个班排 3 门课、每门 1 节，足够在 45 格里求出多个不同排法。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='张老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=1, course='数学', teacher='李老师', periods=1),
        TeachingTask(id=2, grade='初三', class_id=1, course='英语', teacher='王老师', periods=1),
    ]
    return Dataset(grade='初三', classes=[1],
                   teachers={t.teacher: Teacher(name=t.teacher) for t in tasks}, tasks=tasks)


@pytest.fixture()
def tiny_config(tmp_path, monkeypatch):
    import scheduler.api.routes as routes_module
    import scheduler.api.ws as ws_module
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(ws_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    cfg = load_config(CONFIG_DIR)
    dataset = _tiny_feasible_dataset()
    result = ImportResult(dataset=dataset, rules=[], warnings=[])
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_teaching_yaml(result, tmp_path / 'teaching.yaml')
    write_rules_yaml(result, tmp_path / 'rules.generated.yaml')
    for name in ('courses.yaml', 'plans.yaml', 'venues.yaml', 'calendars.yaml'):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text(encoding='utf-8'),
                                     encoding='utf-8')
    return tmp_path


@pytest.fixture()
def config_missing_courses(tmp_path, monkeypatch):
    """故意只写 teaching.yaml，不复制 courses.yaml/plans.yaml/venues.yaml——

    这样 /api/solve 的『还没导入』检查（只看 teaching.yaml 存不存在）会通过，
    真正的失败发生在 _run_job 后台线程里调用 load_config() 时（ConfigError：
    缺少配置文件）。用来验证「_run_job 里任何异常都必须变成一个终结事件」，
    而不是让 WebSocket 客户端永远卡住、GET /api/solve/{job_id} 永远停在旧状态。
    """
    import scheduler.api.routes as routes_module
    import scheduler.api.ws as ws_module
    monkeypatch.setattr(routes_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    monkeypatch.setattr(ws_module, 'DEFAULT_CONFIG_DIR', tmp_path)
    dataset = _tiny_feasible_dataset()
    result = ImportResult(dataset=dataset, rules=[], warnings=[])
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_teaching_yaml(result, tmp_path / 'teaching.yaml')
    write_rules_yaml(result, tmp_path / 'rules.generated.yaml')
    return tmp_path


def _collect_ws_events_with_timeout(client, job_id, timeout=15):
    """在后台线程里跑 WebSocket 接收循环，主线程用 timeout 兜底。

    直接在主线程里死等 ws.receive_json() 的话，一旦回归重新引入
    『_run_job 异常被静默吞掉』的 bug，这个测试会真的卡死、拖垮整个 CI，
    而不是干净地报一个失败。用守护线程 + Queue.get(timeout=...) 把
    『卡住』翻译成一个明确的断言失败。
    """
    result_queue: queue_mod.Queue = queue_mod.Queue()

    def worker():
        try:
            events = []
            with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
                while True:
                    msg = ws.receive_json()
                    events.append(msg)
                    # 'done' 是协议里唯一的终结标记——'error' 之后 _run_job 也总会
                    # 紧跟着补一条 'done'，这里不能提前在 'error' 上 break，否则会
                    # 抢在 solve_ws 转发完 'done' 之前就收工，读到不完整的事件序列。
                    if msg['type'] == 'done':
                        break
            result_queue.put(('ok', events))
        except Exception as exc:  # noqa: BLE001 - 转交给主线程重新抛出
            result_queue.put(('error', exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        status, payload = result_queue.get(timeout=timeout)
    except queue_mod.Empty:
        pytest.fail(
            'WebSocket 在 %d 秒内没有收到 done 终结事件 —— 疑似后台任务异常但'
            '没有推送任何事件，客户端会永久挂起' % timeout)
    if status == 'error':
        raise payload
    return payload


def test_solve_then_websocket_receives_candidates_and_done(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 2, 'min_diff': 1,
                                           'max_seconds': 10})
    assert resp.status_code == 200
    job_id = resp.json()['job_id']

    events = []
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            events.append(msg)
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break

    types = [e['type'] for e in events]
    assert 'solving' in types
    candidates = [e for e in events if e['type'] == 'candidate']
    assert len(candidates) == 2, ('请求 count=2、min_diff=1，tiny 数据集在 45 格里差异空间'
                                  '远大于 1，理应求出 2 个候选：实际 %d 个' % len(candidates))
    assert candidates[0]['status'] == 'OPTIMAL'
    assert candidates[0]['violations'] == []
    assert types[-1] == 'done'

    # 只判断「收到 2 条 candidate 事件」抓不住『min_diff 约束被静默丢掉、
    # 每次都吐同一张表』这类回归——这里直接比较两个候选的落点集合。
    def placed(candidate):
        return {(p['task_id'], p['slot']) for p in candidate['placements']}

    assert placed(candidates[0]) != placed(candidates[1]), '两个候选的排课结果完全相同'


def test_solve_job_status_reachable_via_polling(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    status_resp = client.get('/api/solve/%s' % job_id)
    assert status_resp.status_code == 200
    assert status_resp.json()['status'] == 'done'


def test_solve_job_detail_includes_candidate_placements(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    detail = client.get('/api/solve/%s' % job_id).json()
    assert detail['grade'] == '初三'
    assert len(detail['candidates']) == 1
    assert detail['candidates'][0]['index'] == 1
    assert detail['candidates'][0]['placements']


def test_solve_job_persists_across_a_fresh_lookup(client, tiny_config):
    """求解任务落在 SQLite 而不是进程内存字典——直接用新 job_id 查也能查到，
    不依赖 create_job 返回的那个 Python 对象还留在内存里。"""
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break

    from scheduler.api import sessions
    reloaded = sessions.get_job(job_id)
    assert reloaded is not None
    assert reloaded.status == 'done'
    assert len(reloaded.solutions) == 1


def test_list_solve_jobs_shows_newest_first(client, tiny_config):
    resp1 = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                            'max_seconds': 10})
    job_id1 = resp1.json()['job_id']
    resp2 = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                            'max_seconds': 10})
    job_id2 = resp2.json()['job_id']

    listed = client.get('/api/solve/jobs').json()['jobs']
    ids = [j['job_id'] for j in listed]
    assert ids[:2] == [job_id2, job_id1]


def test_delete_solve_job_removes_it(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    assert client.delete('/api/solve/%s' % job_id).status_code == 200
    assert client.get('/api/solve/%s' % job_id).status_code == 404


def test_delete_solve_job_404_for_unknown_id(client):
    assert client.delete('/api/solve/不存在的job').status_code == 404


def test_clear_solve_jobs_removes_all(client, tiny_config):
    client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                    'max_seconds': 10})
    client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                    'max_seconds': 10})
    assert client.delete('/api/solve/jobs').status_code == 200
    assert client.get('/api/solve/jobs').json()['jobs'] == []


# ---------------------------------------------------------------- 拖拽调整

def _solved_job_id(client):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    return job_id


def test_adjust_applies_a_clean_move(client, tiny_config):
    job_id = _solved_job_id(client)
    detail = client.get('/api/solve/%s' % job_id).json()
    placement = detail['candidates'][0]['placements'][0]
    occupied = {p['slot'] for p in detail['candidates'][0]['placements']}
    free_slot = next(s for s in range(45) if s not in occupied)

    resp = client.post('/api/solve/%s/candidates/1/adjust' % job_id, json={
        'class_id': placement['class_id'],
        'moves': [{'task_id': placement['task_id'], 'to_slot': free_slot}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['applied'] == [placement['task_id']]
    assert body['reverted'] == []
    moved = next(p for p in body['placements'] if p['task_id'] == placement['task_id'])
    assert moved['slot'] == free_slot


def test_adjust_reverts_a_move_that_double_books_the_class(client, tiny_config):
    job_id = _solved_job_id(client)
    detail = client.get('/api/solve/%s' % job_id).json()
    placements = detail['candidates'][0]['placements']
    moving, target = placements[0], placements[1]

    resp = client.post('/api/solve/%s/candidates/1/adjust' % job_id, json={
        'class_id': moving['class_id'],
        'moves': [{'task_id': moving['task_id'], 'to_slot': target['slot']}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['applied'] == []
    assert len(body['reverted']) == 1
    assert body['reverted'][0]['task_id'] == moving['task_id']


def test_adjust_404_for_unknown_job():
    resp = TestClient(app).post('/api/solve/不存在的job/candidates/1/adjust',
                                json={'class_id': 1, 'moves': []})
    assert resp.status_code == 404


def test_adjust_404_for_out_of_range_candidate_index(client, tiny_config):
    job_id = _solved_job_id(client)
    resp = client.post('/api/solve/%s/candidates/99/adjust' % job_id,
                       json={'class_id': 1, 'moves': []})
    assert resp.status_code == 404


def test_adjust_400_when_task_does_not_belong_to_declared_class(client, tiny_config):
    job_id = _solved_job_id(client)
    detail = client.get('/api/solve/%s' % job_id).json()
    task_id = detail['candidates'][0]['placements'][0]['task_id']

    resp = client.post('/api/solve/%s/candidates/1/adjust' % job_id, json={
        'class_id': 9999,
        'moves': [{'task_id': task_id, 'to_slot': 0}],
    })
    assert resp.status_code == 400


def test_export_returns_xlsx_file(client, tiny_config):
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break
    export_resp = client.get('/api/export/%s/1' % job_id)
    assert export_resp.status_code == 200
    assert export_resp.headers['content-type'].startswith(
        'application/vnd.openxmlformats')


def test_export_with_template_returns_404_when_template_file_missing(
        client, tiny_config, monkeypatch):
    """Finding I3：`课程表模板.xlsx` 在新克隆的仓库里本来就不存在（未纳入 git）。

    点『导出 Excel（教务模板版）』时，缺文件不该产生裸 500 + 堆栈，而应该是
    一个说明白原因的 404。用 monkeypatch 模拟『文件缺失』，不碰仓库根目录下
    真实存在的那份模板文件（这份文件是否提交由用户另外决定，与本测试无关）。
    """
    import scheduler.api.routes as routes_module
    monkeypatch.setattr(routes_module, 'TEMPLATE_PATH', tiny_config / '不存在的模板.xlsx')

    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    job_id = resp.json()['job_id']
    with client.websocket_connect('/api/ws/solve/%s' % job_id) as ws:
        while True:
            msg = ws.receive_json()
            if msg['type'] in ('done', 'infeasible', 'precheck_failed'):
                break

    export_resp = client.get('/api/export/%s/1' % job_id, params={'template': 1})
    assert export_resp.status_code == 404
    assert '课程表模板.xlsx' in export_resp.json()['detail']


def test_run_job_exception_still_reaches_websocket_as_terminal_event(
        client, config_missing_courses):
    """Finding 1 回归测试：_run_job 里任何异常都必须变成一个终结事件。

    config_missing_courses 只写了 teaching.yaml，没有 courses.yaml 等——
    /api/solve 本身的『还没导入』检查只看 teaching.yaml 存不存在，会放行；
    真正的失败发生在后台线程调用 load_config() 时抛出 ConfigError。
    在修复之前，这里会导致 WebSocket 客户端与 GET /api/solve/{job_id}
    永远卡住 —— 用带超时的接收循环把「永久挂起」翻译成明确的断言失败。
    """
    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    assert resp.status_code == 200
    job_id = resp.json()['job_id']

    events = _collect_ws_events_with_timeout(client, job_id, timeout=15)

    types = [e['type'] for e in events]
    assert types[-1] == 'done', '异常之后也必须以 done 收尾，客户端才能确定连接可以关闭'
    assert 'error' in types, '后台线程异常必须转成一个 error 事件出声，不能被静默吞掉'

    error_events = [e for e in events if e['type'] == 'error']
    assert error_events[0]['message']   # 必须带上可读的错误信息，不能是空字符串

    status_resp = client.get('/api/solve/%s' % job_id)
    assert status_resp.status_code == 200
    assert status_resp.json()['status'] == 'error', (
        'job.status 必须反映真实的失败状态，不能停留在 pending/solving 让人误以为还在跑')


def test_solve_streaming_produces_distinct_candidates_via_callback():
    """Finding 2a：直接单测 _solve_streaming，隔开 HTTP/WS 层去验证真正的增量语义。

    用真实的初三 32 班数据集（与 tests/test_solve_e2e.py 的
    test_solve_many_returns_distinct_feasible_solutions 同一份数据、同一种
    diff 断言写法）——差异空间够大，才能真正区分『逐个求解并逐个回调』与
    『先算完全部解、再一次性回放』：后者这里同样能让回调触发 3 次，
    但重点是每次回调时求出的候选彼此必须满足 min_diff 差异约束，
    这正是 _solve_streaming 里『约束加到同一个 compiled.model 上』这件事
    的可观察后果。
    """
    from scheduler.api.ws import _solve_streaming

    cfg = load_config(CONFIG_DIR)
    result = import_excel(EXCEL, cfg, grade='初三')
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')

    received = []
    produced, last_status = _solve_streaming(result.dataset, cfg, rules, count=3, min_diff=8,
                                             max_seconds=30, on_candidate=received.append)

    assert produced == len(received), 'on_candidate 的调用次数必须与返回的 produced 数一致'
    assert produced >= 1
    assert last_status in ('OPTIMAL', 'FEASIBLE')
    for sol in received:
        assert sol.feasible

    def placed(sol):
        return {(p.task_id, p.slot) for p in sol.placements}

    for i in range(len(received)):
        for j in range(i + 1, len(received)):
            diff = placed(received[i]) ^ placed(received[j])
            assert len(diff) >= 8, '第 %d 与第 %d 个候选差异只有 %d 处' % (i, j, len(diff))


def test_solve_streaming_returns_last_status_unknown_on_timeout(monkeypatch):
    """Finding I5：_solve_streaming 必须把 CP-SAT 的 UNKNOWN（没跑完，不是无解）
    如实报给调用方，调用方靠这个字段区分『真无解』与『超时未判定』。"""
    from ortools.sat.python import cp_model as cp_model_mod

    from scheduler.api.ws import _solve_streaming

    cfg = load_config(CONFIG_DIR)
    dataset = _tiny_feasible_dataset()
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')

    monkeypatch.setattr(cp_model_mod.CpSolver, 'Solve', lambda self, model: cp_model_mod.UNKNOWN)

    produced, last_status = _solve_streaming(dataset, cfg, rules, count=1, min_diff=1,
                                             max_seconds=1, on_candidate=lambda s: None)
    assert produced == 0
    assert last_status == 'UNKNOWN'


def test_run_job_reports_timeout_not_infeasible_and_skips_minimal_conflict(
        client, tiny_config, monkeypatch):
    """Finding I5 回归测试：求解超时（CP-SAT 返回 UNKNOWN）不能被当成无解处理——

    不能报 'infeasible'（那是已证明无解），也不能烧时间去跑 minimal_conflict
    （对『只是慢、没跑完』的问题算出来的『最小冲突集』没有意义，见 finding 描述）。
    """
    import scheduler.api.ws as ws_module

    def fake_solve_streaming(*args, **kwargs):
        return 0, 'UNKNOWN'

    monkeypatch.setattr(ws_module, '_solve_streaming', fake_solve_streaming)

    conflict_calls = []

    def fake_minimal_conflict(*args, **kwargs):
        conflict_calls.append(1)
        return None

    monkeypatch.setattr(ws_module, 'minimal_conflict', fake_minimal_conflict)

    resp = client.post('/api/solve', json={'grade': '初三', 'count': 1, 'min_diff': 1,
                                           'max_seconds': 10})
    assert resp.status_code == 200
    job_id = resp.json()['job_id']

    events = _collect_ws_events_with_timeout(client, job_id, timeout=15)

    types = [e['type'] for e in events]
    assert 'timeout' in types, '求解超时必须有专门的事件类型，与无解区分开'
    assert 'infeasible' not in types, '超时不能被当成无解上报'
    assert types[-1] == 'done'
    assert conflict_calls == [], 'minimal_conflict 不应该在纯超时场景下被调用'

    status_resp = client.get('/api/solve/%s' % job_id)
    assert status_resp.status_code == 200
    assert status_resp.json()['status'] == 'timeout'
    assert status_resp.json()['status'] != 'infeasible'
