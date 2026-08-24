"""班级课表拖拽调整：一批同班内的挪课，只退肇事者。

不新增一套独立的冲突判断逻辑——`verify()` 已经是这个项目里"一个格子
合不合法"的唯一事实来源（校验器独立于编译器实现，见 CLAUDE.md 铁律4）。
这里把它当黑盒裁判反复调用：套用整批改动，若有冲突就贪心地依次尝试
撤销其中一处，选撤销后违规数降得最多的那个，直到剩下的改动跑 verify()
干净为止。如果找不到"撤销一处能改善"的选择，说明这批改动互相牵连，
退化成整体回退。
"""
from typing import Dict, List

from pydantic import BaseModel

from .solver import Placement, Solution
from .verifier import verify


class RevertedMove(BaseModel):
    task_id: int
    reason: str


class AdjustResult(BaseModel):
    placements: List[Placement]
    applied: List[int] = []
    reverted: List[RevertedMove] = []


def _with_moves_applied(placements: List[Placement], pending: Dict[int, int]) -> List[Placement]:
    return [
        p.model_copy(update={'slot': pending[p.task_id]}) if p.task_id in pending else p
        for p in placements
    ]


def _violation_details(placements: List[Placement], dataset, cfg, rules) -> List[str]:
    solution = Solution(status='OPTIMAL', wall_time=0.0, placements=placements)
    return [v.detail for v in verify(solution, dataset, cfg, rules)]


def apply_and_prune(placements: List[Placement], moves: Dict[int, int],
                    dataset, cfg, rules) -> AdjustResult:
    """moves: task_id -> to_slot，均属于同一 class_id（调用方负责校验）。"""
    if not moves:
        return AdjustResult(placements=placements, applied=[], reverted=[])

    pending = dict(moves)
    reverted: List[RevertedMove] = []

    while pending:
        candidate = _with_moves_applied(placements, pending)
        current = _violation_details(candidate, dataset, cfg, rules)
        if not current:
            return AdjustResult(placements=candidate, applied=list(pending.keys()),
                                reverted=reverted)

        best_task_id = None
        best_count = len(current)
        best_reason = ''
        for task_id in pending:
            trial = dict(pending)
            del trial[task_id]
            trial_candidate = _with_moves_applied(placements, trial)
            trial_details = _violation_details(trial_candidate, dataset, cfg, rules)
            if len(trial_details) < best_count:
                resolved = set(current) - set(trial_details)
                best_task_id = task_id
                best_count = len(trial_details)
                best_reason = '；'.join(sorted(resolved)) if resolved else '存在冲突'

        if best_task_id is None:
            # 没有单独撤销任何一处能改善——这批改动互相牵连，整体回退。
            reverted += [RevertedMove(task_id=tid, reason='与其他改动互相牵连，已整体撤销')
                        for tid in pending]
            return AdjustResult(placements=placements, applied=[], reverted=reverted)

        reverted.append(RevertedMove(task_id=best_task_id, reason=best_reason))
        del pending[best_task_id]

    return AdjustResult(placements=placements, applied=[], reverted=reverted)
