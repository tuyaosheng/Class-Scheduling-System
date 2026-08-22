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
from .schemas import SolveJobCreated, SolveRequest

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'

ws_router = APIRouter(prefix='/api')


def _solve_streaming(dataset, cfg, rules, *, count, min_diff, max_seconds, on_candidate):
    compiled = compile_model(dataset, cfg, rules)
    by_id = {t.id: t for t in dataset.tasks}
    produced = 0
    for _ in range(count):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(max_seconds)
        solver.parameters.num_search_workers = 8
        started = time.time()
        status = solver.Solve(compiled.model)
        elapsed = time.time() - started
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
        solution = Solution(status=_STATUS_NAME.get(status, str(status)),
                            wall_time=elapsed, placements=placements)
        on_candidate(solution)
        produced += 1
        compiled.model.Add(sum(chosen_vars) <= len(chosen_vars) - min_diff)
    return produced


def _run_job(job_id, grade, count, min_diff, max_seconds, loop, queue):
    job = sessions.get_job(job_id)
    cfg = load_config(DEFAULT_CONFIG_DIR)
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    data = yaml.safe_load(teaching_path.read_text(encoding='utf-8'))

    def emit(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    if data['grade'] != grade:
        job.status = 'precheck_failed'
        job.issues = [{'kind': '年级不匹配',
                       'detail': '已导入的数据是 %s，但排课请求指定的是 %s' % (data['grade'], grade)}]
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

    job.dataset, job.cfg = dataset, cfg
    issues = precheck(dataset, cfg, rules)
    if issues:
        job.status = 'precheck_failed'
        job.issues = [{'kind': i.kind, 'detail': i.detail} for i in issues]
        emit({'type': 'precheck_failed', 'issues': job.issues})
        emit({'type': 'done', 'count': 0})
        return

    job.status = 'solving'
    emit({'type': 'solving'})

    def on_candidate(solution):
        idx = len(job.solutions) + 1
        violations = verify(solution, dataset, cfg, rules)
        job.solutions.append(solution)
        job.violations.append(violations)
        emit({
            'type': 'candidate', 'index': idx, 'status': solution.status,
            'wall_time': solution.wall_time,
            'violations': [v.model_dump() for v in violations],
            'placements': [p.model_dump() for p in solution.placements],
        })

    produced = _solve_streaming(dataset, cfg, rules, count=count, min_diff=min_diff,
                                max_seconds=max_seconds, on_candidate=on_candidate)

    if produced == 0:
        job.status = 'infeasible'
        conflict = minimal_conflict(dataset, cfg, rules, max_seconds=max_seconds)
        job.conflict = format_conflict(conflict)
        emit({'type': 'infeasible', 'conflict': job.conflict})
    else:
        job.status = 'done'
    emit({'type': 'done', 'count': produced})


@ws_router.post('/solve', response_model=SolveJobCreated)
async def start_solve(body: SolveRequest):
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if not teaching_path.exists():
        raise HTTPException(status_code=400, detail='还没有导入任课数据，请先完成导入确认')

    job = sessions.create_job()
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    job._queue = queue  # 挂在 job 上，供 WebSocket 端点读取

    loop.run_in_executor(None, _run_job, job.job_id, body.grade, body.count,
                         body.min_diff, body.max_seconds, loop, queue)
    return SolveJobCreated(job_id=job.job_id)


@ws_router.get('/solve/{job_id}')
def solve_status(job_id: str):
    job = sessions.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='任务不存在')
    return {'job_id': job.job_id, 'status': job.status, 'candidates': len(job.solutions)}


@ws_router.websocket('/ws/solve/{job_id}')
async def solve_ws(websocket: WebSocket, job_id: str):
    job = sessions.get_job(job_id)
    if job is None:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    queue = getattr(job, '_queue', None)
    if queue is None:
        await websocket.close(code=4004)
        return
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event['type'] in ('done',):
                break
    except WebSocketDisconnect:
        pass
