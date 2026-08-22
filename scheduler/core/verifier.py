"""独立校验器。

【铁律】本文件不得 import compiler，也不得复用其任何约束逻辑。
编译器面对变量与线性表达式，校验器面对已落定的 placement 直接数数 ——
两套写法互相证伪，「0 处违规」才有意义。
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from . import calendar as cal
from .rules import Rule, select_tasks

PARITIES = ('单周', '双周')


class Violation(BaseModel):
    kind: str
    detail: str
    rule_type: Optional[str] = None
    scope: Dict = Field(default_factory=dict)


def _runs_in_parity(placement, parity):
    return placement.parity is None or placement.parity == parity


def verify(solution, dataset, cfg, rules) -> List[Violation]:
    out: List[Violation] = []
    placements = solution.placements
    out += _check_period_counts(placements, dataset)
    out += _check_class_clash(placements)
    out += _check_teacher_clash(placements, cfg)
    out += _check_venues(placements, cfg)
    for rule in rules:
        if not rule.enabled or rule.mode != 'hard':
            continue
        checker = _RULE_CHECKS.get(rule.type)
        if checker:
            out += checker(placements, dataset, cfg, rule)
    return out


def _check_period_counts(placements, dataset):
    actual = Counter(p.task_id for p in placements)
    out = []
    for task in dataset.tasks:
        if actual[task.id] != task.periods:
            out.append(Violation(
                kind='课时数不符',
                detail='%d班 %s（%s）实排 %d 节，应为 %d 节'
                       % (task.class_id, task.course, task.teacher,
                          actual[task.id], task.periods)))
    return out


def _check_class_clash(placements):
    out = []
    for parity in PARITIES:
        seen = defaultdict(list)
        for p in placements:
            if _runs_in_parity(p, parity):
                seen[(p.class_id, p.slot)].append(p)
        for (class_id, slot), group in seen.items():
            if len(group) > 1:
                day, period = cal.slot_of(slot)
                out.append(Violation(
                    kind='班级重课',
                    detail='%d班 %s第%d节（%s）同时有 %s'
                           % (class_id, cal.DAYS[day], period, parity,
                              '、'.join(p.course for p in group))))
    return _dedup(out)


def _check_teacher_clash(placements, cfg):
    out = []
    for parity in PARITIES:
        seen = defaultdict(list)
        for p in placements:
            if cfg.courses[p.course].multi_class:
                continue                     # 合班课：一位教师可同时面向多个班
            if _runs_in_parity(p, parity):
                seen[(p.teacher, p.slot)].append(p)
        for (teacher, slot), group in seen.items():
            if len(group) > 1:
                day, period = cal.slot_of(slot)
                out.append(Violation(
                    kind='教师分身',
                    detail='%s %s第%d节（%s）同时在 %s'
                           % (teacher, cal.DAYS[day], period, parity,
                              '、'.join('%d班%s' % (p.class_id, p.course) for p in group))))
    return _dedup(out)


def _check_venues(placements, cfg):
    out = []
    for venue in cfg.venues.values():
        if venue.capacity is None:
            continue
        for parity in PARITIES:
            counts = Counter(p.slot for p in placements
                             if cfg.courses[p.course].venue == venue.name
                             and _runs_in_parity(p, parity))
            for slot, count in counts.items():
                if count > venue.capacity:
                    day, period = cal.slot_of(slot)
                    out.append(Violation(
                        kind='场地超容',
                        detail='%s %s第%d节（%s）%d 个班占用，容量 %d'
                               % (venue.name, cal.DAYS[day], period, parity,
                                  count, venue.capacity)))
    return _dedup(out)


def _scoped_placements(placements, dataset, cfg, rule):
    ids = {t.id for t in select_tasks(rule, dataset.tasks, cfg)}
    return [p for p in placements if p.task_id in ids]


def _check_forbid(placements, dataset, cfg, rule):
    banned = {(int(d), int(p)) for d, p in rule.params.get('slots', [])}
    out = []
    for p in _scoped_placements(placements, dataset, cfg, rule):
        if cal.slot_of(p.slot) in banned:
            day, period = cal.slot_of(p.slot)
            out.append(Violation(kind='违反禁排', rule_type=rule.type, scope=rule.scope,
                                 detail='%s %d班%s 排在 %s第%d节'
                                        % (p.teacher, p.class_id, p.course,
                                           cal.DAYS[day], period)))
    return out


def _check_pin(placements, dataset, cfg, rule):
    window = {(int(d), int(p)) for d, p in rule.params.get('slots', [])}
    out = []
    for p in _scoped_placements(placements, dataset, cfg, rule):
        if cal.slot_of(p.slot) not in window:
            day, period = cal.slot_of(p.slot)
            out.append(Violation(kind='越出窗口', rule_type=rule.type, scope=rule.scope,
                                 detail='%d班%s 排在 %s第%d节，不在固定窗口内'
                                        % (p.class_id, p.course, cal.DAYS[day], period)))
    return out


def _daily_counts(placements, dataset, cfg, rule):
    counts = defaultdict(int)
    for p in _scoped_placements(placements, dataset, cfg, rule):
        counts[(p.class_id, cal.slot_of(p.slot)[0])] += 1
    classes = {p.class_id for p in _scoped_placements(placements, dataset, cfg, rule)}
    return counts, classes


def _check_daily_min(placements, dataset, cfg, rule):
    n = int(rule.params['n'])
    counts, classes = _daily_counts(placements, dataset, cfg, rule)
    out = []
    for class_id in sorted(classes):
        for day in range(len(cal.DAYS)):
            if counts[(class_id, day)] < n:
                out.append(Violation(
                    kind='每日下限不足', rule_type=rule.type, scope=rule.scope,
                    detail='%d班 %s %s 仅 %d 节，要求至少 %d 节'
                           % (class_id, rule.scope.get('family', rule.scope.get('course', '')),
                              cal.DAYS[day], counts[(class_id, day)], n)))
    return out


def _check_daily_max(placements, dataset, cfg, rule):
    n = int(rule.params['n'])
    counts, classes = _daily_counts(placements, dataset, cfg, rule)
    out = []
    for (class_id, day), count in sorted(counts.items()):
        if count > n:
            out.append(Violation(
                kind='每日上限超出', rule_type=rule.type, scope=rule.scope,
                detail='%d班 %s %s 排了 %d 节，上限 %d 节'
                       % (class_id, rule.scope.get('family', ''),
                          cal.DAYS[day], count, n)))
    return out


def _check_weekday_exact(placements, dataset, cfg, rule):
    n = int(rule.params['n'])
    days = [cal.day_index(d) for d in rule.params['weekdays']]
    counts, classes = _daily_counts(placements, dataset, cfg, rule)
    out = []
    for class_id in sorted(classes):
        for day in days:
            if counts[(class_id, day)] != n:
                out.append(Violation(
                    kind='指定星期节数不符', rule_type=rule.type, scope=rule.scope,
                    detail='%d班 %s %s 排了 %d 节，要求恰好 %d 节'
                           % (class_id, rule.scope.get('family', ''),
                              cal.DAYS[day], counts[(class_id, day)], n)))
    return out


def _check_consecutive(placements, dataset, cfg, rule):
    days_needed = int(rule.params.get('days', 1))
    length = int(rule.params.get('length', 2))
    by_class = defaultdict(set)
    for p in _scoped_placements(placements, dataset, cfg, rule):
        by_class[p.class_id].add(cal.slot_of(p.slot))
    out = []
    for class_id, slots in sorted(by_class.items()):
        runs = 0
        for day in range(len(cal.DAYS)):
            periods = sorted(p for d, p in slots if d == day)
            for start in periods:
                block = list(range(start, start + length))
                if block[-1] > cal.PERIODS_PER_DAY:
                    continue
                if 5 in block[:-1] and 6 in block:      # 跨午休不算连堂
                    continue
                if all(p in periods for p in block):
                    runs += 1
                    break
        if runs < days_needed:
            out.append(Violation(
                kind='缺少连堂', rule_type=rule.type, scope=rule.scope,
                detail='%d班 %s 有 %d 天连堂，要求 %d 天'
                       % (class_id, rule.scope.get('course', ''), runs, days_needed)))
    return out


def _check_alternate(placements, dataset, cfg, rule):
    first, second = rule.params['pair']
    by_class = defaultdict(lambda: defaultdict(set))
    for p in _scoped_placements(placements, dataset, cfg, rule):
        by_class[p.class_id][p.course].add(p.slot)
    out = []
    for class_id, courses in sorted(by_class.items()):
        a, b = courses.get(first), courses.get(second)
        if a is None or b is None:
            continue
        if a != b:
            out.append(Violation(
                kind='单双周未共格', rule_type=rule.type, scope=rule.scope,
                detail='%d班 %s 与 %s 未占用同一时间格' % (class_id, first, second)))
    return out


_RULE_CHECKS = {
    'forbid_slots': _check_forbid,
    'pin_window': _check_pin,
    'daily_min': _check_daily_min,
    'daily_max': _check_daily_max,
    'weekday_exact': _check_weekday_exact,
    'consecutive': _check_consecutive,
    'alternate_weeks': _check_alternate,
}


def _dedup(violations):
    seen, out = set(), []
    for v in violations:
        key = (v.kind, v.detail)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def format_violations(violations) -> str:
    if not violations:
        return '校验通过：0 处违规。'
    grouped = defaultdict(list)
    for v in violations:
        grouped[v.kind].append(v.detail)
    lines = ['校验发现 %d 处违规：' % len(violations)]
    for kind in sorted(grouped):
        lines.append('[%s] %d 处' % (kind, len(grouped[kind])))
        lines.extend('  ' + d for d in grouped[kind][:10])
        if len(grouped[kind]) > 10:
            lines.append('  ...另有 %d 处' % (len(grouped[kind]) - 10))
    return '\n'.join(lines)
