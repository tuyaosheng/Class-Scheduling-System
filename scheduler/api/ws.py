"""求解任务的后台执行与 WebSocket 事件推送。

不调用 core/solver.py 的 solve_many（它是一次性返回全部结果的阻塞函数，
没有逐个候选的回调钩子），而是照 solve_many 内部同样的算法——用
compile_model 编译一次模型，每求出一个候选就加一条『与它相比至少
min_diff 处不同』的约束再求下一个——但在这里每求出一个就调用一次
on_candidate 回调，从而做到真正的逐帧推送。这是 compiler.py/verifier.py
已经确立的『宁可重复、不做耦合』先例的同一种做法：core/solver.py 不改。
"""
import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from ortools.sat.python import cp_model

import yaml

from scheduler.core.compiler import compile_model
from scheduler.core.config import load_config
from scheduler.core.diagnose import format_conflict, minimal_conflict
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.precheck import precheck
from scheduler.core.rules import load_rules
from scheduler.core.solver import Placement, Solution, _STATUS_NAME
from scheduler.core.verifier import verify

from . import sessions
from .schemas import (
    CandidateItem, SolveJobCreated, SolveJobDetail, SolveJobSummary,
    SolveJobsListResponse, SolveRequest,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'

ws_router = APIRouter(prefix='/api')

# 求解任务本身持久化在 SQLite（sessions.py），但 WebSocket 推送用的
# asyncio.Queue 是连接期间的运行时管道，既不可序列化也不该持久化——
# 单独用一个进程内字典按 job_id 追踪，随连接生命周期增删。
_job_queues: dict = {}


def _solve_streaming(dataset, cfg, rules, *, count, min_diff, max_seconds, on_candidate):
    """返回 (produced, last_status)。

    last_status 是最后一次 solver.Solve() 看到的 CP-SAT 状态名（如 'INFEASIBLE'
    'UNKNOWN' 'OPTIMAL'）——调用方需要它来区分『真正被证明无解』与『求解超时、
    没跑出结论』，这两者不是一回事，不能都当无解处理（见 CLAUDE.md「L1/L2/L3」
    与本轮 finding I5）。循环一次都没跑（count<=0）时 last_status 为 None。
    """
    compiled = compile_model(dataset, cfg, rules)
    by_id = {t.id: t for t in dataset.tasks}
    produced = 0
    last_status = None
    for _ in range(count):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(max_seconds)
        solver.parameters.num_search_workers = 8
        started = time.time()
        status = solver.Solve(compiled.model)
        elapsed = time.time() - started
        last_status = _STATUS_NAME.get(status, str(status))
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        chosen_vars = []
        placements = []
        for (task_id, slot), var in compiled.x.items():
            if solver.Value(var):
                chosen_vars.append(var)
                task = by_id[task_id]
                placements.append(Placement(
                    task_id=task_id, class_id=task.class_id, course=task.course,
                    teacher=task.teacher, slot=slot, parity=task.parity))
        placements.sort(key=lambda p: (p.class_id, p.slot))
        solution = Solution(status=last_status,
                            wall_time=elapsed, placements=placements)
        on_candidate(solution)
        produced += 1
        compiled.model.Add(sum(chosen_vars) <= len(chosen_vars) - min_diff)
    return produced, last_status


def _run_job(job_id, grade, count, min_diff, max_seconds, loop, queue):
    """在后台线程里跑完一整个求解任务。

    这段代码运行在 run_in_executor 的工作线程里，返回的 future 没人等待、
    没人 await——任何未捕获的异常都会被线程静默吞掉：WebSocket 客户端会永远
    卡在 `await queue.get()`，`GET /api/solve/{job_id}` 会一直报旧状态，
    与「还在正常求解」无法区分。所以整个函数体必须包在 try/except 里，
    确保不管哪一步炸了，队列里终归会出现一个终结事件（error + done）。
    """
    job = sessions.get_job(job_id)

    def emit(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    try:
        cfg = load_config(DEFAULT_CONFIG_DIR)
        teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
        data = yaml.safe_load(teaching_path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or 'grade' not in data:
            raise ValueError('teaching.yaml 内容损坏或缺少 grade 字段')

        if data['grade'] != grade:
            job.status = 'precheck_failed'
            job.issues = [{'kind': '年级不匹配',
                           'detail': '已导入的数据是 %s，但排课请求指定的是 %s'
                                     % (data['grade'], grade)}]
            sessions.save_job(job)
            emit({'type': 'precheck_failed', 'issues': job.issues})
            emit({'type': 'done', 'count': 0})
            return

        dataset = Dataset(
            grade=data['grade'], classes=data['classes'],
            teachers={t['name']: Teacher(**t) for t in data['teachers']},
            tasks=[TeachingTask(**t) for t in data['tasks']],
        )
        rules = load_rules(DEFAULT_CONFIG_DIR / 'rules.yaml',
                           DEFAULT_CONFIG_DIR / 'rules.generated.yaml')

        job.dataset, job.cfg, job.rules = dataset, cfg, rules
        sessions.save_job(job)
        issues = precheck(dataset, cfg, rules)
        if issues:
            job.status = 'precheck_failed'
            job.issues = [{'kind': i.kind, 'detail': i.detail} for i in issues]
            sessions.save_job(job)
            emit({'type': 'precheck_failed', 'issues': job.issues})
            emit({'type': 'done', 'count': 0})
            return

        job.status = 'solving'
        sessions.save_job(job)
        emit({'type': 'solving'})

        def on_candidate(solution):
            idx = len(job.solutions) + 1
            violations = verify(solution, dataset, cfg, rules)
            job.solutions.append(solution)
            job.violations.append(violations)
            sessions.save_job(job)
            emit({
                'type': 'candidate', 'index': idx, 'status': solution.status,
                'wall_time': solution.wall_time,
                'violations': [v.model_dump() for v in violations],
                'placements': [p.model_dump() for p in solution.placements],
            })

        produced, last_status = _solve_streaming(
            dataset, cfg, rules, count=count, min_diff=min_diff,
            max_seconds=max_seconds, on_candidate=on_candidate)

        if produced == 0 and last_status == 'UNKNOWN':
            # 求解超时，CP-SAT 没能判定可行性——不是无解，是没跑完。
            # 这种情况下 minimal_conflict 本身还要再烧一次最多 max_seconds，
            # 而且对『仅仅是慢』的问题算出来的『最小冲突集』毫无意义，直接跳过。
            job.status = 'timeout'
            message = ('求解超时（%d 秒内未判定是否可行），这不代表无解，只是没跑完——'
                      '可以提高最大求解时长后重试' % max_seconds)
            job.conflict = message
            emit({'type': 'timeout', 'message': message})
        elif produced == 0:
            job.status = 'infeasible'
            conflict = minimal_conflict(dataset, cfg, rules, max_seconds=max_seconds)
            job.conflict = format_conflict(conflict)
            emit({'type': 'infeasible', 'conflict': job.conflict})
        else:
            job.status = 'done'
        sessions.save_job(job)
        emit({'type': 'done', 'count': produced})
    except Exception as exc:
        job.status = 'error'
        message = '求解任务异常终止（%s）：%s' % (type(exc).__name__, exc)
        job.conflict = message
        sessions.save_job(job)
        emit({'type': 'error', 'message': message})
        emit({'type': 'done', 'count': 0})


@ws_router.post('/solve', response_model=SolveJobCreated)
async def start_solve(body: SolveRequest):
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if not teaching_path.exists():
        raise HTTPException(status_code=400, detail='还没有导入任课数据，请先完成导入确认')

    job = sessions.create_job(body.grade)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _job_queues[job.job_id] = queue

    loop.run_in_executor(None, _run_job, job.job_id, body.grade, body.count,
                         body.min_diff, body.max_seconds, loop, queue)
    return SolveJobCreated(job_id=job.job_id)


@ws_router.get('/solve/jobs', response_model=SolveJobsListResponse)
def list_solve_jobs():
    return SolveJobsListResponse(jobs=[SolveJobSummary(**row) for row in sessions.list_jobs()])


@ws_router.delete('/solve/jobs')
def clear_solve_jobs():
    sessions.clear_jobs()
    return {'ok': True}


@ws_router.get('/solve/{job_id}', response_model=SolveJobDetail)
def solve_status(job_id: str):
    job = sessions.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='任务不存在')
    candidates = [
        CandidateItem(
            index=i + 1, status=solution.status, wall_time=solution.wall_time,
            violations=[v.model_dump() for v in violations],
            placements=[p.model_dump() for p in solution.placements],
        )
        for i, (solution, violations) in enumerate(zip(job.solutions, job.violations))
    ]
    return SolveJobDetail(job_id=job.job_id, status=job.status, grade=job.grade,
                          candidates=candidates, issues=job.issues, conflict=job.conflict)


@ws_router.delete('/solve/{job_id}')
def delete_solve_job(job_id: str):
    if sessions.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail='任务不存在')
    sessions.delete_job(job_id)
    return {'ok': True}


@ws_router.websocket('/ws/solve/{job_id}')
async def solve_ws(websocket: WebSocket, job_id: str):
    job = sessions.get_job(job_id)
    if job is None:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    queue = _job_queues.get(job_id)
    if queue is None:
        await websocket.close(code=4004)
        return
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event['type'] in ('done',):
                # 'error' 之后 _run_job 也总会紧跟着补一条 'done'（见 _run_job 的
                # except 分支），所以协议里唯一的终结标记始终是 'done'——这里不需要
                # 也不应该额外在 'error' 上提前 break，否则 'done' 事件会被丢在
                # 队列里没人转发，破坏「done 是终结事件」这个不变量。
                break
    except WebSocketDisconnect:
        pass
    finally:
        _job_queues.pop(job_id, None)
