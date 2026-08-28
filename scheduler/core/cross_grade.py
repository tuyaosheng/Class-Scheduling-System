"""跨年级教师冲突：求解阶段就避开，不是排完了再事后校验。

各年级仍然独立求解（现有单年级引擎不用改），但求解某个年级之前，先把
其它年级"最近一次求解出的第一个候选方案"当作既定事实，按教师姓名 +
真实钟点区间换算成本年级的 forbid_slots 硬约束——这样同一位老师就不会
被两个年级同时排到同一个真实时刻，从源头上不产生冲突，不需要导出前
再跑一遍检测（原来的做法，已废弃，见 CLAUDE.md 子项目9设计变更）。

不能比较"第几节"，因为不同年级的作息形状（节数、午休边界、钟点表）
可能不一样，必须换算成真实的（星期几, 起止钟点）区间才能判断是否重叠。

这一层独立于单年级的 verify()，不共享 class_id/compiler.x 键空间（见
CLAUDE.md「M7 前置重构」一节：那里说的"合排"特指塞进同一个 CP-SAT 模型
统一求解，这里只是求解某年级前，把其它年级的既定事实转成普通的
forbid_slots 规则喂给同一个单年级编译器，不涉及那两条缺口）。
"""
from collections import defaultdict
from typing import Dict, List, Tuple

from .models import Dataset, GradeCalendar
from .solver import Solution


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def compute_cross_grade_lock_rules(
    grade: str, calendar: GradeCalendar,
    other_entries: Dict[str, Tuple[Dataset, Solution]],
) -> List[dict]:
    """把 other_entries（其它年级 -> (dataset, 已锁定的候选方案)）换算成
    `grade` 自己坐标系下的 forbid_slots 规则列表（每位跨年级任课的教师一条）。

    `calendar` 或某个其它年级没配 `clock_times` 时，涉及该方（或全部）的
    换算直接跳过——没法按真实时间比较，宁可不生成约束，也不能拿"第几节"
    硬凑出一个可能是错的禁排。
    """
    if not calendar.clock_times:
        return []

    external_by_teacher: Dict[str, List[Tuple[str, int, int]]] = defaultdict(list)
    for other_grade, (other_dataset, other_solution) in other_entries.items():
        if other_grade == grade:
            continue
        other_calendar = other_dataset.calendar
        if not other_calendar.clock_times:
            continue
        for p in other_solution.placements:
            day_idx, period = other_calendar.slot_of(p.slot)
            if period - 1 >= len(other_calendar.clock_times):
                continue
            day_name = other_calendar.days[day_idx]
            start, end = other_calendar.clock_times[period - 1]
            external_by_teacher[p.teacher].append((day_name, _to_minutes(start), _to_minutes(end)))

    rules: List[dict] = []
    for teacher in sorted(external_by_teacher):
        windows_by_day: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        for day_name, start_min, end_min in external_by_teacher[teacher]:
            windows_by_day[day_name].append((start_min, end_min))

        forbidden = set()
        for day_idx, day_name in enumerate(calendar.days):
            day_windows = windows_by_day.get(day_name)
            if not day_windows:
                continue
            for period in range(1, calendar.periods_per_day + 1):
                if period - 1 >= len(calendar.clock_times):
                    continue
                start, end = calendar.clock_times[period - 1]
                s_min, e_min = _to_minutes(start), _to_minutes(end)
                if any(s_min < we and ws < e_min for ws, we in day_windows):
                    forbidden.add((day_idx, period))

        if forbidden:
            rules.append({
                'type': 'forbid_slots',
                'scope': {'grade': grade, 'teacher': teacher},
                'params': {'slots': sorted([d, p] for d, p in forbidden)},
                'mode': 'hard',
            })
    return rules
