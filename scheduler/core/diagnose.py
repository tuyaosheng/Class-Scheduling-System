"""L2 最小冲突集。

预检通过但仍无解时才跑这一层。给可放松的规则挂 assumption 开关，
无解后由 CP-SAT 返回最小矛盾子集 —— AI 拿到的是确定性事实，不会幻觉。
"""
from typing import List

from ortools.sat.python import cp_model
from pydantic import BaseModel

from .compiler import compile_model
from .rules import describe

_STATUS_NAME = {
    cp_model.OPTIMAL: 'OPTIMAL',
    cp_model.FEASIBLE: 'FEASIBLE',
    cp_model.INFEASIBLE: 'INFEASIBLE',
    cp_model.MODEL_INVALID: 'MODEL_INVALID',
    cp_model.UNKNOWN: 'UNKNOWN',
}


class Conflict(BaseModel):
    status: str
    rules: List[str] = []


def minimal_conflict(dataset, cfg, rules, *, max_seconds=60) -> Conflict:
    compiled = compile_model(dataset, cfg, rules, with_assumptions=True)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_seconds)
    # SufficientAssumptionsForInfeasibility 仅在单 worker 下可靠
    solver.parameters.num_search_workers = 1

    status = solver.Solve(compiled.model)
    if status != cp_model.INFEASIBLE:
        return Conflict(status=_STATUS_NAME.get(status, str(status)))

    seen, descriptions = set(), []
    for index in solver.SufficientAssumptionsForInfeasibility():
        rule = compiled.assumptions.get(index)
        if rule is None:
            continue
        text = describe(rule)
        if text not in seen:
            seen.add(text)
            descriptions.append(text)
    return Conflict(status='INFEASIBLE', rules=descriptions)


def format_conflict(conflict: Conflict) -> str:
    if conflict.status != 'INFEASIBLE':
        return '模型可解（状态 %s），无冲突集。' % conflict.status
    if not conflict.rules:
        return ('状态 INFEASIBLE，但冲突集为空 —— 说明矛盾来自不可放松的约束'
                '（教师不分身 / 班级不重课 / 固定窗口 / 禁排）。请回看预检输出。')
    lines = ['状态 INFEASIBLE，冲突集含 %d 条规则：' % len(conflict.rules)]
    lines += ['  • ' + r for r in conflict.rules]
    lines.append('松绑其中任意一条即可能有解。')
    return '\n'.join(lines)
