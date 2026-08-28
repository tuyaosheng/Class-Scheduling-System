"""跨年级统一校验：导出全部课表前，按教师姓名 + 真实钟点区间比对多个年级
的排课冲突。

各年级独立求解，互不知道彼此存在——同一位教师如果同时在两个年级任课，
理论上可能被两个年级各自排在"同一时刻"。这里不能比较"第几节"，因为
不同年级的作息形状（节数、午休边界、钟点表）可能不一样，必须换算成
真实的（星期几, 起止钟点）区间才能判断是否重叠。

这一层独立于单年级的 verify()，不共享 class_id/compiler.x 键空间（见
CLAUDE.md「M7 前置重构」一节：那里说的"合排"特指塞进同一个 CP-SAT 模型
统一求解，这里只是求解完之后额外比对一次，不涉及那两条缺口）。
"""
from collections import defaultdict
from typing import Dict, List, Tuple

from pydantic import BaseModel

from .models import Dataset
from .solver import Solution


class CrossGradeConflict(BaseModel):
    teacher: str
    day: str
    grade_a: str
    class_a: int
    course_a: str
    start_a: str
    end_a: str
    grade_b: str
    class_b: int
    course_b: str
    start_b: str
    end_b: str


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def find_cross_grade_conflicts(
    entries: Dict[str, Tuple[Dataset, Solution]],
) -> Tuple[List[CrossGradeConflict], List[str]]:
    """entries: grade -> (dataset, solution)。

    返回 (冲突列表, 因缺少真实钟点表而被跳过的年级列表)——年级日历没配
    `clock_times` 时没法按真实时间比较，宁可跳过并提示，也不能瞎猜。
    """
    events = []   # (teacher, day, start_min, end_min, start_str, end_str, grade, class_id, course)
    skipped: List[str] = []
    for grade, (dataset, solution) in entries.items():
        calendar = dataset.calendar
        if not calendar.clock_times:
            skipped.append(grade)
            continue
        for p in solution.placements:
            day_idx, period = calendar.slot_of(p.slot)
            if period - 1 >= len(calendar.clock_times):
                continue
            day_name = calendar.days[day_idx]
            start, end = calendar.clock_times[period - 1]
            events.append((p.teacher, day_name, _to_minutes(start), _to_minutes(end),
                          start, end, grade, p.class_id, p.course))

    by_teacher_day = defaultdict(list)
    for ev in events:
        by_teacher_day[(ev[0], ev[1])].append(ev)

    conflicts: List[CrossGradeConflict] = []
    for items in by_teacher_day.values():
        items.sort(key=lambda e: e[2])
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a[6] == b[6]:
                    continue   # 同年级内部冲突已经由各自的 verify() 保证不存在
                if a[2] < b[3] and b[2] < a[3]:   # 区间重叠
                    conflicts.append(CrossGradeConflict(
                        teacher=a[0], day=a[1],
                        grade_a=a[6], class_a=a[7], course_a=a[8], start_a=a[4], end_a=a[5],
                        grade_b=b[6], class_b=b[7], course_b=b[8], start_b=b[4], end_b=b[5],
                    ))
    return conflicts, sorted(skipped)
