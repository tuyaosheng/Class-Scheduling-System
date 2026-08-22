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
        for (task_id, slot), var in compiled.x.items():
            if solver.Value(var):
                task = by_id[task_id]
                placements.append(Placement(
                    task_id=task_id, class_id=task.class_id, course=task.course,
                    teacher=task.teacher, slot=slot, parity=task.parity))
        placements.sort(key=lambda p: (p.class_id, p.slot))
    return Solution(status=_STATUS_NAME.get(status, str(status)),
                    wall_time=elapsed, placements=placements)
