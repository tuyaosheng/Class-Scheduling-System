"""独立校验器。

【铁律】本文件不得 import compiler，也不得复用其任何约束逻辑。
编译器面对变量与线性表达式，校验器面对已落定的 placement 直接数数 ——
两套写法互相证伪，「0 处违规」才有意义。
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from . import calendar as cal
from .rules import Rule, describe, select_tasks

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
        if checker is None:
            # 静默放行会把「0 违规」变成空话。校验器的语义是收集问题，
            # 所以这里出声而不抛错 —— 其余检查照常跑完。
            out.append(Violation(
                kind='规则未被校验', rule_type=rule.type, scope=rule.scope,
                detail='硬规则 %s 尚无对应的校验实现，本次未被检查：%s'
                       % (rule.type, describe(rule))))
            continue
        out += checker(placements, dataset, cfg, rule)
    return out


def verify_soft(solution, dataset, cfg, rules) -> List[Violation]:
    """只跑软规则，独立于硬校验 —— 不污染「0 处违规」的硬保证。

    软约束的语义是「尽量满足」，这里把未满足处作为提示列出，供教务权衡。
    """
    out: List[Violation] = []
    placements = solution.placements
    for rule in rules:
        if not rule.enabled or rule.mode != 'soft':
            continue
        checker = _SOFT_CHECKS.get(rule.type)
        if checker is None:
            continue
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


def _engagement(placement, cfg):
    """这节课对「谁在忙」而言算作哪一件事。

    合班课整门折叠成一件事（同一位教师面向多个班，本来就只是一节课）；
    其余课程一节就是一件事。返回 (识别键, 人话标签)。
    """
    if cfg.courses[placement.course].multi_class:
        return ('合班', placement.teacher, placement.course), '%s（合班）' % placement.course
    return (('独立', placement.task_id),
            '%d班%s' % (placement.class_id, placement.course))


def _check_teacher_clash(placements, cfg):
    """一位教师在某一格若有两件**不同的事**，就是分身。

    合班课的多个班折叠后只剩一件事，所以合班本身不会触发；
    但它与该教师的其他课仍然互斥 —— 合班不等于分身。
    """
    agenda = defaultdict(dict)           # (教师, 时间格, 周次) -> {识别键: 标签}
    for p in placements:
        for parity in PARITIES:
            if _runs_in_parity(p, parity):
                key, label = _engagement(p, cfg)
                agenda[(p.teacher, p.slot, parity)][key] = label
    out = []
    for (teacher, slot, parity), items in agenda.items():
        if len(items) > 1:
            day, period = cal.slot_of(slot)
            out.append(Violation(
                kind='教师分身',
                detail='%s %s第%d节（%s）同时在 %s'
                       % (teacher, cal.DAYS[day], period, parity,
                          '、'.join(sorted(items.values())))))
    return _dedup(out)


def _venue_load(placements, cfg, venue_name, parity):
    """某场地在各时间格上的占位数。合班课整门只占 1 处，不按班数。"""
    load = defaultdict(set)
    for p in placements:
        if cfg.courses[p.course].venue != venue_name:
            continue
        if not _runs_in_parity(p, parity):
            continue
        load[p.slot].add(_engagement(p, cfg)[0])
    return {slot: len(keys) for slot, keys in load.items()}


def _venue_overflow(placements, cfg, venue_name, capacity):
    out = []
    for parity in PARITIES:
        for slot, count in sorted(_venue_load(placements, cfg, venue_name, parity).items()):
            if count > capacity:
                day, period = cal.slot_of(slot)
                out.append(Violation(
                    kind='场地超容',
                    detail='%s %s第%d节（%s）%d 处占用（合班课整门计 1 处），容量 %d'
                           % (venue_name, cal.DAYS[day], period, parity, count, capacity)))
    return out


def _check_venues(placements, cfg):
    out = []
    for venue in cfg.venues.values():
        if venue.capacity is not None:
            out += _venue_overflow(placements, cfg, venue.name, venue.capacity)
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


def _watched_days(rule):
    """规则声明了 weekdays 就只判这几天，否则整周都判。

    忽略它会对未被约束的日子报假违规 —— DSL 是教务直接编辑的界面，
    校验器一旦被当成噪声，真问题就再没人看了。
    """
    names = rule.params.get('weekdays')
    if not names:
        return None                      # None = 不设限，整周都判
    return {cal.day_index(name) for name in names}


def _check_daily_min(placements, dataset, cfg, rule):
    n = int(rule.params['n'])
    watched = _watched_days(rule)
    counts, classes = _daily_counts(placements, dataset, cfg, rule)
    days = sorted(watched) if watched is not None else range(len(cal.DAYS))
    out = []
    for class_id in sorted(classes):
        for day in days:
            if counts[(class_id, day)] < n:
                out.append(Violation(
                    kind='每日下限不足', rule_type=rule.type, scope=rule.scope,
                    detail='%d班 %s %s 仅 %d 节，要求至少 %d 节'
                           % (class_id, rule.scope.get('family', rule.scope.get('course', '')),
                              cal.DAYS[day], counts[(class_id, day)], n)))
    return out


def _check_daily_max(placements, dataset, cfg, rule):
    n = int(rule.params['n'])
    watched = _watched_days(rule)
    counts, classes = _daily_counts(placements, dataset, cfg, rule)
    out = []
    for (class_id, day), count in sorted(counts.items()):
        if watched is not None and day not in watched:
            continue
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


def _check_venue_capacity(placements, dataset, cfg, rule):
    """规则驱动的场地容量。与配置驱动的 _check_venues 是两条独立路径。"""
    capacity = rule.params.get('capacity')
    if capacity is None:
        return []
    out = _venue_overflow(placements, cfg, rule.params['venue'], int(capacity))
    for v in out:
        v.rule_type, v.scope = rule.type, rule.scope
    return out


def _check_teacher_max_run(placements, dataset, cfg, rule):
    """独立计数：每位教师×每个半天，有没有「≥max_len+1 节」的连堂段。

    与 compiler 的 _compile_teacher_max_run 完全独立 —— 这里只数已落定的
    placement，不碰任何变量。单双周按周次分开看；合班课的多个班在同一格
    只算教师占一次（同一 slot 进同一集合即去重）。

    同一物理连堂段（周课在单双两周都上课）只报一次，标注「每周」；
    只在某一周次出现的标注该周次。
    """
    max_len = int(rule.params.get('max_len', 2))
    threshold = max_len + 1

    # (teacher, parity, day) -> 该天该周次被占的节次集合
    occ = defaultdict(set)
    for p in placements:
        for parity in PARITIES:
            if _runs_in_parity(p, parity):
                day, period = cal.slot_of(p.slot)
                occ[(p.teacher, parity, day)].add(period)

    # 按 (teacher, day, 半天, 起点, 长度) 聚合，跨周次去重
    found = {}                # key -> 出现的周次列表
    for (teacher, parity, day), periods in occ.items():
        for half, half_label in ((cal.MORNING, '上午'), (cal.AFTERNOON, '下午')):
            present = sorted(p for p in half if p in periods)
            if len(present) < threshold:
                continue
            i = 0
            while i < len(present):
                j = i
                while j + 1 < len(present) and present[j + 1] == present[j] + 1:
                    j += 1
                start_p, length = present[i], j - i + 1
                i = j + 1
                if length < threshold:
                    continue
                key = (teacher, day, half_label, start_p, length)
                found.setdefault(key, []).append(parity)

    out = []
    for (teacher, day, half_label, start_p, length), parities in sorted(found.items()):
        parities = sorted(parities)
        pw = '每周' if len(parities) == 2 else parities[0]
        end_p = start_p + length - 1
        out.append(Violation(
            kind='教师半天连堂过长', rule_type=rule.type, scope=rule.scope,
            detail='%s %s（%s）%s 第%d-%d节 连续 %d 节'
                   '（要求半天不超过 %d 节）'
                   % (teacher, cal.DAYS[day], pw, half_label,
                      start_p, end_p, length, max_len)))
    return out


_RULE_CHECKS = {
    'forbid_slots': _check_forbid,
    'pin_window': _check_pin,
    'daily_min': _check_daily_min,
    'daily_max': _check_daily_max,
    'weekday_exact': _check_weekday_exact,
    'consecutive': _check_consecutive,
    'alternate_weeks': _check_alternate,
    'venue_capacity': _check_venue_capacity,
}

_SOFT_CHECKS = {
    'teacher_max_run': _check_teacher_max_run,
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
