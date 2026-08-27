"""L1 预检：求解前的毫秒级确定性检查。

绝大多数「排不出来」是容量或口径问题，不该劳烦求解器 ——
同一个场景求解器跑 19 秒只吐 INFEASIBLE，这里瞬间指出缺几节课。
"""
from collections import defaultdict
from typing import List

from pydantic import BaseModel

from .rules import select_tasks


class Issue(BaseModel):
    kind: str
    detail: str


def precheck(dataset, cfg, rules) -> List[Issue]:
    issues: List[Issue] = []
    issues += _check_teacher_capacity(dataset, cfg)
    issues += _check_class_capacity(dataset, cfg)
    issues += _check_rule_contradictions(dataset, cfg, rules)
    issues += _check_pin_windows(dataset, cfg, rules)
    issues += _check_venue_capacity(dataset, cfg)
    return issues


def _teacher_demand(dataset):
    demand = defaultdict(int)
    for task in dataset.tasks:
        demand[task.teacher] += task.periods
    return demand


def _check_teacher_capacity(dataset, cfg) -> List[Issue]:
    demand = _teacher_demand(dataset)
    reserved = cfg.reserved_slot_indices(dataset.grade)
    n_slots = dataset.calendar.n_slots
    out = []
    for name, needed in sorted(demand.items()):
        teacher = dataset.teachers.get(name)
        personal = {dataset.calendar.slot_index(d, p) for d, p in teacher.forbidden} if teacher else set()
        blocked = len(personal | reserved)
        available = n_slots - blocked
        if needed > available:
            out.append(Issue(
                kind='教师超载',
                detail='%s 需要 %d 节，但可用时段只有 %d 格'
                       '（全周 %d 格，被禁排/教务固定占位共占用 %d 格）→ 缺 %d 格'
                       % (name, needed, available, n_slots, blocked, needed - available)))
    return out


def _check_class_capacity(dataset, cfg) -> List[Issue]:
    used = defaultdict(int)
    for task in dataset.tasks:
        if task.consumes_slot:
            used[task.class_id] += task.periods
    n_slots = dataset.calendar.n_slots
    available = n_slots - len(cfg.reserved_slot_indices(dataset.grade))
    return [Issue(kind='班级超载',
                  detail='%d班 需占 %d 格，每周可用 %d 格（教务固定占位 %d 格）→ 超 %d 格'
                         % (class_id, total, available, n_slots - available, total - available))
            for class_id, total in sorted(used.items()) if total > available]


def _family_totals(dataset, cfg, rule):
    totals = defaultdict(int)
    for task in select_tasks(rule, dataset.tasks, cfg):
        totals[task.class_id] += task.periods
    return totals


def _scope_label(rule):
    return (rule.scope.get('family') or rule.scope.get('course')
            or rule.scope.get('teacher') or '该学科')


def _check_rule_contradictions(dataset, cfg, rules) -> List[Issue]:
    out = []
    n_days = len(dataset.calendar.days)
    for rule in rules:
        if not rule.enabled or rule.mode != 'hard':
            continue
        if rule.type == 'daily_min':
            n = int(rule.params['n'])
            for class_id, total in sorted(_family_totals(dataset, cfg, rule).items()):
                if total < n * n_days:
                    out.append(Issue(
                        kind='规则自相矛盾',
                        detail='%d班 %s 周课时仅 %d 节，却要求「每天至少 %d 节」'
                               '（一周 %d 天至少需 %d 节）'
                               % (class_id, _scope_label(rule), total, n, n_days, n * n_days)))
        elif rule.type == 'daily_max':
            n = int(rule.params['n'])
            for class_id, total in sorted(_family_totals(dataset, cfg, rule).items()):
                if total > n * n_days:
                    out.append(Issue(
                        kind='规则自相矛盾',
                        detail='%d班 %s 周课时 %d 节，却要求「每天至多 %d 节」'
                               '（一周 %d 天最多只能放 %d 节）'
                               % (class_id, _scope_label(rule), total, n, n_days, n * n_days)))
        elif rule.type == 'weekday_exact':
            n = int(rule.params['n'])
            needed = n * len(rule.params['weekdays'])
            for class_id, total in sorted(_family_totals(dataset, cfg, rule).items()):
                if total < needed:
                    out.append(Issue(
                        kind='规则自相矛盾',
                        detail='%d班 %s 周课时仅 %d 节，却要求 %s 各 %d 节（共需 %d 节）'
                               % (class_id, _scope_label(rule), total,
                                  '、'.join(rule.params['weekdays']), n, needed)))
    return out


def _check_pin_windows(dataset, cfg, rules) -> List[Issue]:
    out = []
    for rule in rules:
        if rule.type != 'pin_window' or not rule.enabled:
            continue
        window = len(rule.params.get('slots', []))
        for task in select_tasks(rule, dataset.tasks, cfg):
            if task.periods > window:
                out.append(Issue(
                    kind='固定窗口容量不足',
                    detail='%d班 %s 需排 %d 节，固定窗口只有 %d 格'
                           % (task.class_id, task.course, task.periods, window)))
    return out


def _venue_demand(dataset, cfg, venue_name) -> int:
    """场地占位需求：按任务累加占用节数。"""
    courses = cfg.courses_of(dataset.grade)
    total = 0
    for task in dataset.tasks:
        if courses[task.course].venue != venue_name:
            continue
        total += task.periods
    return total


def _check_venue_capacity(dataset, cfg) -> List[Issue]:
    out = []
    n_slots = dataset.calendar.n_slots
    for venue in cfg.venues.values():
        if venue.capacity is None:
            continue
        demand = _venue_demand(dataset, cfg, venue.name)
        supply = venue.capacity * n_slots
        if demand > supply:
            out.append(Issue(
                kind='场地容量不足',
                detail='%s 总需求 %d 节，容量 %d 间 × %d 格 = %d → 缺 %d'
                       % (venue.name, demand, venue.capacity, n_slots,
                          supply, demand - supply)))
    return out


def format_issues(issues) -> str:
    if not issues:
        return '预检通过：未发现容量或口径问题。'
    return '\n'.join('[%s] %s' % (i.kind, i.detail) for i in issues)
