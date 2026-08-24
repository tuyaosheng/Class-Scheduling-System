"""班级课表拖拽调整：一批同班内的挪课，只退肇事者。

不新增一套独立的冲突判断逻辑——`verify()` 已经是这个项目里"一个格子
合不合法"的唯一事实来源（校验器独立于编译器实现，见 CLAUDE.md 铁律4）。
这里把它当黑盒裁判反复调用：套用整批改动，若有冲突就贪心地依次尝试
撤销其中一处，选撤销后违规数降得最多的那个，直到剩下的改动跑 verify()
干净为止。如果找不到"撤销一处能改善"的选择，说明这批改动互相牵连，
退化成整体回退。

一个 task_id 未必只对应一处 placement——周课时 > 1 的课（绝大多数课都
是）在 `solution.placements` 里会有多条记录共用同一个 task_id，只是
slot 不同。所以"要挪动哪一节课"不能只用 task_id 识别，必须是
(task_id, from_slot) 这一对才能唯一定位到具体某一节课。只用 task_id
当 key 会把该任务的全部节次一起拖去同一个目标格——这个 bug 在人工点开
浏览器实测时才暴露，所有单元测试用的都是周课时=1 的任务，task_id 和
"这一节课"恰好是一一对应，掩盖了这个问题。
"""
from typing import Dict, List, Tuple

from pydantic import BaseModel

from .solver import Placement, Solution
from .verifier import verify

MoveKey = Tuple[int, int]   # (task_id, from_slot)


class RevertedMove(BaseModel):
    task_id: int
    from_slot: int
    reason: str


class AdjustResult(BaseModel):
    placements: List[Placement]
    applied: List[MoveKey] = []
    reverted: List[RevertedMove] = []


def _with_moves_applied(placements: List[Placement], pending: Dict[MoveKey, int]) -> List[Placement]:
    return [
        p.model_copy(update={'slot': pending[(p.task_id, p.slot)]})
        if (p.task_id, p.slot) in pending else p
        for p in placements
    ]


def _violation_details(placements: List[Placement], dataset, cfg, rules) -> List[str]:
    solution = Solution(status='OPTIMAL', wall_time=0.0, placements=placements)
    return [v.detail for v in verify(solution, dataset, cfg, rules)]


def apply_and_prune(placements: List[Placement], moves: Dict[MoveKey, int],
                    dataset, cfg, rules) -> AdjustResult:
    """moves: (task_id, from_slot) -> to_slot，均属于同一 class_id（调用方负责校验）。"""
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

        best_key = None
        best_count = len(current)
        best_reason = ''
        for key in pending:
            trial = dict(pending)
            del trial[key]
            trial_candidate = _with_moves_applied(placements, trial)
            trial_details = _violation_details(trial_candidate, dataset, cfg, rules)
            if len(trial_details) < best_count:
                resolved = set(current) - set(trial_details)
                best_key = key
                best_count = len(trial_details)
                best_reason = '；'.join(sorted(resolved)) if resolved else '存在冲突'

        if best_key is None:
            # 没有单独撤销任何一处能改善——这批改动互相牵连，整体回退。
            reverted += [RevertedMove(task_id=tid, from_slot=from_slot,
                                     reason='与其他改动互相牵连，已整体撤销')
                        for tid, from_slot in pending]
            return AdjustResult(placements=placements, applied=[], reverted=reverted)

        task_id, from_slot = best_key
        reverted.append(RevertedMove(task_id=task_id, from_slot=from_slot, reason=best_reason))
        del pending[best_key]

    return AdjustResult(placements=placements, applied=[], reverted=reverted)
