"""M7：多年级合排——把多个年级的 CP-SAT 子问题放进同一个模型联合求解。

各年级自己的建模逻辑完全不变（`compile_model` 逐年级调用，只是共享同一个
`cp_model.CpModel()`，靠 `compile_model(..., model=, finalize=False)` 两个
参数做到）；这一层只额外做两件事：

  1. 求解前把各年级的 task id 重新编号成全局唯一——各年级导入时都是从 0
     开始编号，直接合并会在 `CompiledModel.x` 字典里互相覆盖（见 CLAUDE.md
     「M7 前置重构」）。`class_id` 不需要类似处理：每个年级的班级唯一性
     约束只在该年级自己那次 `compile_model` 调用里生效（一次调用只看得到
     一个年级的 `dataset.tasks`），天然不会跟别的年级的班号混在一起。

  2. 跨年级联动约束：同一位教师在多个年级任课时、或多个年级共用同一个
     没有单独分配容量的场地时，按真实钟点区间避免被同时占用——不是比较
     "第几节"，因为参与合排的年级作息形状可能不同（见 cross_grade.py
     同样的口径）。这一层取代了子项目9"求解阶段单向避让"的近似做法：
     合排是真正联合求解，不存在"谁先求解谁说了算"的顺序依赖。

「各年级独立求解」（`solver.py::solve`/`solve_many`）继续保留、不受影响——
合排是"要保证联合可行时"的额外选项，不是唯一路径（用户明确要求两者并存）。
"""
from collections import defaultdict
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from .compiler import PARITIES, active_in, compile_model
from .cross_grade import _to_minutes
from .models import Dataset, GradeCalendar
from .rules import Rule
from .solver import _extract_placements, _STATUS_NAME, Solution


class MergedCompiledModel:
    def __init__(self, model, compiled_by_grade, original_id_by_grade):
        self.model = model
        self.compiled_by_grade = compiled_by_grade   # grade -> CompiledModel（task id 是重编号后的全局 id）
        # grade -> {重编号后的全局 id: 调用方原始 Dataset 里的 task id}——
        # solve_merged 用它把结果的 task_id 换回调用方认得的编号，否则
        # placement.task_id 对不上调用方自己那份 Dataset.tasks 的 id，
        # 下游 exporter/adjust 之类按 task_id 查 task 会直接 KeyError。
        self.original_id_by_grade = original_id_by_grade


def _renumber_tasks(datasets: Dict[str, Dataset]) -> Tuple[Dict[str, Dataset], Dict[str, Dict[int, int]]]:
    """把每个年级的 task id 改写成全局唯一，返回 (新 Dataset, 新id->原id 映射)，原对象不变。"""
    next_id = 0
    out = {}
    original_id_by_grade: Dict[str, Dict[int, int]] = {}
    for grade, dataset in datasets.items():
        remapped = []
        id_map = {}
        for t in dataset.tasks:
            id_map[next_id] = t.id
            remapped.append(t.model_copy(update={'id': next_id}))
            next_id += 1
        out[grade] = dataset.model_copy(update={'tasks': remapped})
        original_id_by_grade[grade] = id_map
    return out, original_id_by_grade


def _time_bucket_boundaries(calendars: Dict[str, GradeCalendar]) -> Dict[str, List[int]]:
    """按星期几分组，返回 day_name -> 排序去重后的边界分钟数列表。

    所有参与年级的每一节课的起止时刻，合在一起排序去重，就是能同时兼容
    所有年级作息形状的"最细公共时间格"边界——第 i 个 bucket 是
    [boundaries[i], boundaries[i+1])，任何一个年级的任何一节课要么完整
    覆盖某个 bucket，要么跟它完全不相交，不会出现"半节课"这种情况。
    """
    boundaries_by_day: Dict[str, set] = defaultdict(set)
    for calendar in calendars.values():
        if not calendar.clock_times:
            continue
        for day_name in calendar.days:
            for start, end in calendar.clock_times:
                boundaries_by_day[day_name].add(_to_minutes(start))
                boundaries_by_day[day_name].add(_to_minutes(end))
    return {day: sorted(mins) for day, mins in boundaries_by_day.items()}


def _slot_buckets(calendar: GradeCalendar, boundaries_by_day: Dict[str, List[int]]
                  ) -> Dict[int, List[Tuple[str, int]]]:
    """预算一个年级每个 slot 覆盖的 (星期, bucket 序号) 列表——只依赖日历，
    跟具体任务无关，每个年级只用算一次。"""
    out: Dict[int, List[Tuple[str, int]]] = {}
    if not calendar.clock_times:
        return out
    for slot in range(calendar.n_slots):
        day_idx, period = calendar.slot_of(slot)
        if period - 1 >= len(calendar.clock_times):
            continue
        day_name = calendar.days[day_idx]
        start, end = calendar.clock_times[period - 1]
        s_min, e_min = _to_minutes(start), _to_minutes(end)
        boundaries = boundaries_by_day.get(day_name, [])
        buckets = [(day_name, i) for i in range(len(boundaries) - 1)
                  if s_min <= boundaries[i] and boundaries[i + 1] <= e_min]
        out[slot] = buckets
    return out


def _add_cross_grade_teacher_no_clash(model, compiled_by_grade, boundaries_by_day) -> None:
    """同一位教师在任意两个参与年级都不能被排到真实时间重叠的两节课——
    按 (星期, bucket, 教师, 单双周) 分组收集所有相关年级的占用布尔量，
    总和 <= 1。单年级内部已经被 `_add_teacher_no_clash` 保证过，这里对
    只涉及一个年级的分组是重复约束，无害，不特殊处理。"""
    terms_by_key: Dict[tuple, list] = defaultdict(list)
    for grade, compiled in compiled_by_grade.items():
        slot_buckets = _slot_buckets(compiled.calendar, boundaries_by_day)
        for task in compiled.dataset.tasks:
            for slot in range(compiled.calendar.n_slots):
                buckets = slot_buckets.get(slot)
                if not buckets:
                    continue
                for parity in PARITIES:
                    if not active_in(task, parity):
                        continue
                    var = compiled.x[(task.id, slot)]
                    for day_name, bucket_idx in buckets:
                        terms_by_key[(day_name, bucket_idx, task.teacher, parity)].append(var)

    for terms in terms_by_key.values():
        if len(terms) > 1:
            model.Add(sum(terms) <= 1)


def _add_cross_grade_venue_capacity(model, compiled_by_grade, cfg, boundaries_by_day) -> None:
    """共享场地（没有任何参与年级对它设置 grade_capacity 单独分配）跨年级
    也要遵守总容量——每个年级内部的 `add_venue_constraints` 已经保证了
    "单年级内不超容量"，这里额外加"多个年级同一真实时刻加起来也不超容量"。
    """
    grades = list(compiled_by_grade)
    for venue in cfg.venues.values():
        if venue.capacity is None:
            continue
        if any(g in venue.grade_capacity for g in grades):
            continue   # 任一年级单独分配了这个场地，就不算跨年级共享，跳过

        terms_by_key: Dict[tuple, list] = defaultdict(list)
        for grade, compiled in compiled_by_grade.items():
            courses = cfg.courses_of(grade)
            tasks = [t for t in compiled.dataset.tasks
                    if courses.get(t.course) and courses[t.course].venue == venue.name]
            if not tasks:
                continue
            slot_buckets = _slot_buckets(compiled.calendar, boundaries_by_day)
            for task in tasks:
                for slot in range(compiled.calendar.n_slots):
                    buckets = slot_buckets.get(slot)
                    if not buckets:
                        continue
                    for parity in PARITIES:
                        if not active_in(task, parity):
                            continue
                        var = compiled.x[(task.id, slot)]
                        for day_name, bucket_idx in buckets:
                            terms_by_key[(day_name, bucket_idx, parity)].append(var)

        for terms in terms_by_key.values():
            if len(terms) > venue.capacity:
                model.Add(sum(terms) <= venue.capacity)


def compile_merged_model(datasets: Dict[str, Dataset], cfg,
                         rules_by_grade: Dict[str, List[Rule]]) -> MergedCompiledModel:
    datasets, original_id_by_grade = _renumber_tasks(datasets)
    model = cp_model.CpModel()
    compiled_by_grade = {}
    for grade, dataset in datasets.items():
        compiled_by_grade[grade] = compile_model(
            dataset, cfg, rules_by_grade.get(grade, []), model=model, finalize=False)

    boundaries_by_day = _time_bucket_boundaries(
        {grade: c.calendar for grade, c in compiled_by_grade.items()})
    _add_cross_grade_teacher_no_clash(model, compiled_by_grade, boundaries_by_day)
    _add_cross_grade_venue_capacity(model, compiled_by_grade, cfg, boundaries_by_day)

    all_soft_terms = [term for c in compiled_by_grade.values() for term in c.soft_terms]
    if all_soft_terms:
        model.Minimize(sum(w * v for v, w in all_soft_terms))

    return MergedCompiledModel(model, compiled_by_grade, original_id_by_grade)


def solve_merged(datasets: Dict[str, Dataset], cfg, rules_by_grade: Dict[str, List[Rule]],
                 *, max_seconds=60, workers=8) -> Dict[str, Solution]:
    """联合求解多个年级，返回 grade -> Solution。跟 `solver.solve()` 一样只求
    一个解——合排本来就是为了保证"这几个年级放在一起是可行的"，多候选方案
    的比选留给各年级独立求解那条路径（`solve_many`），这里不重复做。"""
    merged = compile_merged_model(datasets, cfg, rules_by_grade)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(max_seconds)
    solver.parameters.num_search_workers = workers
    status = solver.Solve(merged.model)
    has_soft_terms = any(c.soft_terms for c in merged.compiled_by_grade.values())

    solutions: Dict[str, Solution] = {}
    for grade, compiled in merged.compiled_by_grade.items():
        placements = []
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            by_id = {t.id: t for t in compiled.dataset.tasks}
            placements, _ = _extract_placements(solver, compiled, by_id)
            id_map = merged.original_id_by_grade[grade]
            placements = [p.model_copy(update={'task_id': id_map[p.task_id]}) for p in placements]
        solutions[grade] = Solution(
            status=_STATUS_NAME.get(status, str(status)),
            wall_time=solver.WallTime(),
            placements=placements,
            objective=solver.ObjectiveValue() if has_soft_terms else None,
            stats=solver.ResponseStats(),
        )
    return solutions
