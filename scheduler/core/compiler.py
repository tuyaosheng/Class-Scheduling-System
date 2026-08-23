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
        # 软约束惩罚项：[(惩罚布尔量, 权重), ...]，循环结束后聚合成目标
        self.soft_terms: List = []
        # 教师占用布尔量缓存：(teacher, parity, slot) -> BoolVar
        self.teacher_occ: Dict = {}

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
        if rule.mode == 'hard':
            _RULE_HANDLERS[rule.type](compiled, rule, with_assumptions)
        else:
            # 软约束：有专门处理器就编译进目标，没有则记录为跳过
            soft_handler = _SOFT_HANDLERS.get(rule.type)
            if soft_handler is None:
                compiled.skipped_soft.append(rule)
            else:
                soft_handler(compiled, rule)
    add_venue_constraints(compiled)
    if compiled.soft_terms:
        compiled.model.Minimize(sum(w * v for v, w in compiled.soft_terms))
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
    """连堂是**班级视角**的属性：两节相邻的语文对学生就是连堂，

    哪怕由两位教师分带。所以这里按班聚合命中任务的占用，不绑定单个 task。
    """
    days_needed = int(rule.params.get('days', 1))
    length = int(rule.params.get('length', 2))
    pairs = adjacent_pairs()
    for class_id, tasks in _group_by_class(select_tasks(rule, c.dataset.tasks, c.cfg)).items():
        day_flags = []
        for day in range(len(cal.DAYS)):
            hit = {}                     # 节次 -> 「该班这一格上的是本规则命中的课」

            def hit_var(period, _day=day, _class_id=class_id, _tasks=tasks):
                var = hit.get(period)
                if var is None:
                    var = c.model.NewBoolVar('cons_hit_%d_%d_%d' % (_class_id, _day, period))
                    slot = cal.slot_index(_day, period)
                    # 半具体化：var 为真则这一格至少有一节命中课；由哪个 task 提供不限
                    c.model.Add(
                        sum(c.x[(t.id, slot)] for t in _tasks) >= 1).OnlyEnforceIf(var)
                    hit[period] = var
                return var

            day_indicators = []          # 这一天的全部 y
            for start, _ in pairs:
                run_periods = list(range(start, start + length))
                if run_periods[-1] > cal.PERIODS_PER_DAY:
                    continue
                if any((p, p + 1) in NO_ADJACENT for p in run_periods[:-1]):
                    continue
                y = c.model.NewBoolVar('cons_%d_%d_%d' % (class_id, day, start))
                # 半具体化：y 为真则整段都被命中课占满；反向不需要
                c.model.AddBoolAnd([hit_var(p) for p in run_periods]).OnlyEnforceIf(y)
                day_indicators.append(y)
            if not day_indicators:
                continue
            flag = c.model.NewBoolVar('cons_day_%d_%d' % (class_id, day))
            c.model.AddBoolOr(day_indicators).OnlyEnforceIf(flag)   # flag ⇒ 这天至少一处连堂
            day_flags.append(flag)
        if not day_flags:
            continue
        constraint = c.model.Add(sum(day_flags) >= days_needed)
        lit = _guarded(c, rule, with_assumptions)
        if lit is not None:
            constraint.OnlyEnforceIf(lit)


@handler('venue_capacity')
def _compile_venue_capacity(c: CompiledModel, rule: Rule, with_assumptions: bool) -> None:
    venue = rule.params['venue']
    capacity = rule.params.get('capacity')
    if capacity is None:
        return
    _limit_venue(c, venue, int(capacity))


def _limit_venue(c: CompiledModel, venue: str, capacity: int) -> None:
    tasks = [t for t in c.dataset.tasks if c.cfg.courses[t.course].venue == venue]
    if not tasks:
        return
    for parity in PARITIES:
        active = [t for t in tasks if active_in(t, parity)]
        if len(active) <= capacity:
            continue
        for slot in range(cal.N_SLOTS):
            c.model.Add(sum(c.x[(t.id, slot)] for t in active) <= capacity)


def add_venue_constraints(c: CompiledModel) -> None:
    """按 venues.yaml 的容量自动加约束。capacity 为 None 表示不限制。"""
    for venue in c.cfg.venues.values():
        if venue.capacity is not None:
            _limit_venue(c, venue.name, venue.capacity)


# ---------------------------------------------------------------- 软约束

_SOFT_HANDLERS = {}


def soft_handler(rule_type):
    def register(fn):
        _SOFT_HANDLERS[rule_type] = fn
        return fn
    return register


def _halfday_run_starts(length=3):
    """每个半天内、长度为 length 的连续窗口的起始节次。

    半天边界（5|6）天然隔断——午休那对不算相邻，所以「连续 length 节」
    不可能跨半天，这里按 cal.MORNING/AFTERNOON 各自枚举。
    """
    starts = []
    for half in (cal.MORNING, cal.AFTERNOON):
        for i in range(len(half) - length + 1):
            starts.append(half[i])
    return starts


def _teacher_occ_var(c: CompiledModel, teacher, parity, slot, tasks):
    """教师在指定周次的某一格是否在上课（布尔量）。

    与 _add_teacher_no_clash 同口径——同一教师同一格最多一件事。
    """
    key = (teacher, parity, slot)
    var = c.teacher_occ.get(key)
    if var is not None:
        return var
    var = c.model.NewBoolVar('tocc_%s_%s_%d' % (teacher, parity, slot))
    terms = [c.x[(t.id, slot)] for t in tasks]
    c.model.Add(sum(terms) >= 1).OnlyEnforceIf(var)
    c.model.Add(sum(terms) == 0).OnlyEnforceIf(var.Not())
    c.teacher_occ[key] = var
    return var


@soft_handler('teacher_max_run')
def _compile_teacher_max_run(c: CompiledModel, rule: Rule) -> None:
    """教师半天连堂不超过 max_len 节（软约束，最小化违规数）。

    对每位教师×每个半天，枚举长度为 max_len+1 的连续窗口；窗口三节全占
    即记一次违规。单双周按周次各算占用，但同一物理连堂（周课两周都上课）
    只计一次——用 OR(run_单, run_双) 折叠，避免周课被罚两遍。
    """
    max_len = int(rule.params.get('max_len', 2))
    weight = int(rule.weight) or 1
    window_len = max_len + 1
    starts = _halfday_run_starts(window_len)

    by_teacher = defaultdict(list)
    for t in c.dataset.tasks:
        by_teacher[t.teacher].append(t)

    for teacher, tasks in sorted(by_teacher.items()):
        by_parity = {p: [t for t in tasks if active_in(t, p)] for p in PARITIES}
        active_periods = {p: sum(t.periods for t in by_parity[p]) for p in PARITIES}
        if all(active_periods[p] < window_len for p in PARITIES):
            continue                      # 两个周次都凑不出 window_len 连堂
        for day in range(len(cal.DAYS)):
            for start in starts:
                ps = list(range(start, start + window_len))
                run_by_parity = []
                for p in PARITIES:
                    if active_periods[p] < window_len:
                        continue
                    occs = [_teacher_occ_var(c, teacher, p, cal.slot_index(day, pp), by_parity[p])
                            for pp in ps]
                    rv = c.model.NewBoolVar(
                        'trun_%s_%s_%d_%d' % (teacher, p, day, start))
                    c.model.AddBoolAnd(occs).OnlyEnforceIf(rv)
                    c.model.AddBoolOr([v.Not() for v in occs]).OnlyEnforceIf(rv.Not())
                    run_by_parity.append(rv)
                if not run_by_parity:
                    continue
                # 任一周次出现连堂即记一次（周课两周都算，但 OR 折叠不重复计）
                run = c.model.NewBoolVar('trun_%s_%d_%d' % (teacher, day, start))
                c.model.AddBoolOr(run_by_parity).OnlyEnforceIf(run)
                c.model.AddBoolAnd([v.Not() for v in run_by_parity]).OnlyEnforceIf(run.Not())
                c.soft_terms.append((run, weight))
