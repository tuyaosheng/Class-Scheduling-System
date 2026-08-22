"""规则 → CP-SAT 约束。

【铁律】本文件与 verifier.py 不得共享任何约束逻辑代码。
复用会让同一个 bug 同时骗过编译与校验两侧，「0 处违规」就失去意义。
"""
from collections import defaultdict
from typing import Dict, List

from ortools.sat.python import cp_model

from . import calendar as cal
from .rules import Rule, select_tasks

PARITIES = ('单周', '双周')


def active_in(task, parity: str) -> bool:
    """任务在指定周次是否上课。parity 为 None 的任务每周都上。"""
    return task.parity is None or task.parity == parity


class CompiledModel:
    def __init__(self, model, x, dataset, cfg):
        self.model = model
        self.x: Dict = x
        self.dataset = dataset
        self.cfg = cfg
        self.assumptions: Dict[int, Rule] = {}
        self.skipped_soft: List[Rule] = []

    def task_vars(self, task_id):
        return [self.x[(task_id, s)] for s in range(cal.N_SLOTS)]


def compile_model(dataset, cfg, rules, *, with_assumptions=False) -> CompiledModel:
    model = cp_model.CpModel()
    x = {(t.id, s): model.NewBoolVar('x_%d_%d' % (t.id, s))
         for t in dataset.tasks for s in range(cal.N_SLOTS)}
    compiled = CompiledModel(model, x, dataset, cfg)

    _add_period_counts(compiled)
    _add_class_no_clash(compiled)
    _add_teacher_no_clash(compiled)

    for rule in rules:
        if not rule.enabled:
            continue
        if rule.mode != 'hard':
            compiled.skipped_soft.append(rule)   # 软约束是 M4 的事
            continue
        _RULE_HANDLERS[rule.type](compiled, rule, with_assumptions)
    return compiled


def _add_period_counts(c: CompiledModel) -> None:
    for task in c.dataset.tasks:
        c.model.Add(sum(c.task_vars(task.id)) == task.periods)


def _add_class_no_clash(c: CompiledModel) -> None:
    by_class = defaultdict(list)
    for task in c.dataset.tasks:
        by_class[task.class_id].append(task)
    for tasks in by_class.values():
        for parity in PARITIES:
            active = [t for t in tasks if active_in(t, parity)]
            if len(active) < 2:
                continue
            for slot in range(cal.N_SLOTS):
                c.model.Add(sum(c.x[(t.id, slot)] for t in active) <= 1)


def _add_teacher_no_clash(c: CompiledModel) -> None:
    by_teacher = defaultdict(list)
    for task in c.dataset.tasks:
        if c.cfg.courses[task.course].multi_class:
            continue                      # 合班课豁免：一位教师可同时面向多个班
        by_teacher[task.teacher].append(task)
    for tasks in by_teacher.values():
        for parity in PARITIES:
            active = [t for t in tasks if active_in(t, parity)]
            if len(active) < 2:
                continue
            for slot in range(cal.N_SLOTS):
                c.model.Add(sum(c.x[(t.id, slot)] for t in active) <= 1)


# 各规则类型的编译函数在 Task 9-11 逐个填入
_RULE_HANDLERS = {}


def handler(rule_type):
    def register(fn):
        _RULE_HANDLERS[rule_type] = fn
        return fn
    return register


def _slot_set(rule):
    """params.slots（[[day, period], ...]）→ 扁平索引集合。"""
    return {cal.slot_index(int(d), int(p)) for d, p in rule.params.get('slots', [])}


@handler('forbid_slots')
def _compile_forbid_slots(c: CompiledModel, rule: Rule, with_assumptions: bool) -> None:
    slots = _slot_set(rule)
    for task in select_tasks(rule, c.dataset.tasks, c.cfg):
        for slot in slots:
            c.model.Add(c.x[(task.id, slot)] == 0)


@handler('pin_window')
def _compile_pin_window(c: CompiledModel, rule: Rule, with_assumptions: bool) -> None:
    window = _slot_set(rule)
    for task in select_tasks(rule, c.dataset.tasks, c.cfg):
        for slot in range(cal.N_SLOTS):
            if slot not in window:
                c.model.Add(c.x[(task.id, slot)] == 0)


def _slots_of_day(day):
    return [cal.slot_index(day, p) for p in range(1, cal.PERIODS_PER_DAY + 1)]


def _group_by_class(tasks):
    grouped = defaultdict(list)
    for task in tasks:
        grouped[task.class_id].append(task)
    return grouped


def _guarded(c: CompiledModel, rule: Rule, with_assumptions: bool):
    """需要时给一条约束挂 assumption 开关，供 L2 取回最小冲突集。"""
    if not (with_assumptions and rule.relaxable):
        return None
    lit = c.model.NewBoolVar('assume_%s_%d' % (rule.type, len(c.assumptions)))
    c.model.AddAssumption(lit)
    c.assumptions[lit.Index()] = rule
    return lit


def _add_daily(c: CompiledModel, rule: Rule, with_assumptions: bool, op: str) -> None:
    """按 (班级 × 天) 聚合命中任务的节数。

    注：这里不按单双周拆分 —— Excel 现有数据中心美家族只产出 alternate_weeks，
    不产出 daily_*。若将来某个单双周学科系需要 daily 规则，须在此按周次拆开统计。
    """
    n = int(rule.params['n'])
    weekdays = rule.params.get('weekdays')
    days = [cal.day_index(d) for d in weekdays] if weekdays else range(len(cal.DAYS))
    for tasks in _group_by_class(select_tasks(rule, c.dataset.tasks, c.cfg)).values():
        for day in days:
            total = sum(c.x[(t.id, s)] for t in tasks for s in _slots_of_day(day))
            constraint = {'>=': lambda: c.model.Add(total >= n),
                          '<=': lambda: c.model.Add(total <= n),
                          '==': lambda: c.model.Add(total == n)}[op]()
            lit = _guarded(c, rule, with_assumptions)
            if lit is not None:
                constraint.OnlyEnforceIf(lit)


@handler('daily_min')
def _compile_daily_min(c, rule, with_assumptions):
    _add_daily(c, rule, with_assumptions, '>=')


@handler('daily_max')
def _compile_daily_max(c, rule, with_assumptions):
    _add_daily(c, rule, with_assumptions, '<=')


@handler('weekday_exact')
def _compile_weekday_exact(c, rule, with_assumptions):
    _add_daily(c, rule, with_assumptions, '==')


# 跨午休的 (5, 6) 不算相邻，对应 calendar.yaml 的 no_adjacent
NO_ADJACENT = frozenset({(5, 6)})


def adjacent_pairs():
    """一天之内可构成连堂的节次对。"""
    return [(p, p + 1) for p in range(1, cal.PERIODS_PER_DAY)
            if (p, p + 1) not in NO_ADJACENT]


@handler('alternate_weeks')
def _compile_alternate_weeks(c: CompiledModel, rule: Rule, with_assumptions: bool) -> None:
    """把单双周课程对绑到同一时间格。

    两门课分属不同教师、不同周次，共用一格不构成冲突 ——
    教师/班级不分身约束已按周次分组处理（见 _add_teacher_no_clash）。
    """
    first, second = rule.params['pair']
    for class_id, tasks in _group_by_class(select_tasks(rule, c.dataset.tasks, c.cfg)).items():
        a = [t for t in tasks if t.course == first]
        b = [t for t in tasks if t.course == second]
        if not a or not b:
            continue                     # 缺一半就跳过，容量问题交给预检层报
        for ta in a:
            for tb in b:
                for slot in range(cal.N_SLOTS):
                    c.model.Add(c.x[(ta.id, slot)] == c.x[(tb.id, slot)])


@handler('consecutive')
def _compile_consecutive(c: CompiledModel, rule: Rule, with_assumptions: bool) -> None:
    days_needed = int(rule.params.get('days', 1))
    length = int(rule.params.get('length', 2))
    pairs = adjacent_pairs()
    for class_id, tasks in _group_by_class(select_tasks(rule, c.dataset.tasks, c.cfg)).items():
        indicators = []
        for task in tasks:
            for day in range(len(cal.DAYS)):
                for start, _ in pairs:
                    run_periods = list(range(start, start + length))
                    if run_periods[-1] > cal.PERIODS_PER_DAY:
                        continue
                    if any((p, p + 1) in NO_ADJACENT for p in run_periods[:-1]):
                        continue
                    y = c.model.NewBoolVar('cons_%d_%d_%d_%d' % (class_id, task.id, day, start))
                    # 半具体化：y 为真则整段都是这门课；反向不需要
                    c.model.AddBoolAnd(
                        [c.x[(task.id, cal.slot_index(day, p))] for p in run_periods]
                    ).OnlyEnforceIf(y)
                    indicators.append(y)
        if not indicators:
            continue
        constraint = c.model.Add(sum(indicators) >= days_needed)
        lit = _guarded(c, rule, with_assumptions)
        if lit is not None:
            constraint.OnlyEnforceIf(lit)
