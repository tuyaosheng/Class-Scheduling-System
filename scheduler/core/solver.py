"""两阶段求解的第一阶段：仅硬约束，求任意可行解。

第二阶段（软约束加权优化 + AddHint 热启动）是 M4 的事。
"""
import time
from typing import List, Optional

from ortools.sat.python import cp_model
from pydantic import BaseModel

from . import calendar as cal
from .compiler import compile_model

_STATUS_NAME = {
    cp_model.OPTIMAL: 'OPTIMAL',
    cp_model.FEASIBLE: 'FEASIBLE',
    cp_model.INFEASIBLE: 'INFEASIBLE',
    cp_model.MODEL_INVALID: 'MODEL_INVALID',
    cp_model.UNKNOWN: 'UNKNOWN',
}


class Placement(BaseModel):
    task_id: int
    class_id: int
    course: str
    teacher: str
    slot: int
    parity: Optional[str] = None

    @property
    def day(self) -> int:
        return cal.slot_of(self.slot)[0]

    @property
    def period(self) -> int:
        return cal.slot_of(self.slot)[1]


class Solution(BaseModel):
    status: str
    wall_time: float
    placements: List[Placement] = []

    @property
    def feasible(self) -> bool:
        return self.status in ('OPTIMAL', 'FEASIBLE')


def _extract_placements(solver, compiled, by_id):
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
    return placements, chosen_vars


def solve(dataset, cfg, rules, *, max_seconds=60, workers=8) -> Solution:
    compiled = compile_model(dataset, cfg, rules)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_seconds)
    solver.parameters.num_search_workers = workers

    started = time.time()
    status = solver.Solve(compiled.model)
    elapsed = time.time() - started

    placements = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        by_id = {t.id: t for t in dataset.tasks}
        placements, _ = _extract_placements(solver, compiled, by_id)
    return Solution(status=_STATUS_NAME.get(status, str(status)),
                    wall_time=elapsed, placements=placements)


def solve_many(dataset, cfg, rules, *, count=3, min_diff=8,
               max_seconds=60, workers=8) -> List[Solution]:
    """求多个彼此有差异的可行解，供人工挑选——不是按软约束打分排序。

    每求出一个解就加一条约束：下一个解与它相比，至少 min_diff 个任务的
    时间格不同。约束在同一个模型里累积，所以第 3 个解与第 1、2 个解都保持
    差异，不会退化成同一张表反复输出。求不满 count 个就提前结束，不报错——
    差异空间本就有限，能求出几个算几个。
    """
    compiled = compile_model(dataset, cfg, rules)
    by_id = {t.id: t for t in dataset.tasks}
    solutions: List[Solution] = []
    for _ in range(count):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(max_seconds)
        solver.parameters.num_search_workers = workers

        started = time.time()
        status = solver.Solve(compiled.model)
        elapsed = time.time() - started
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break

        placements, chosen_vars = _extract_placements(solver, compiled, by_id)
        solutions.append(Solution(status=_STATUS_NAME.get(status, str(status)),
                                  wall_time=elapsed, placements=placements))
        compiled.model.Add(sum(chosen_vars) <= len(chosen_vars) - min_diff)
    return solutions
