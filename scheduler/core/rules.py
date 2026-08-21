"""规则 DSL：声明与作用域匹配。

这里只有规则的**声明**和**选取**，没有任何约束语义 ——
语义分别由 compiler.py（编译成 CP-SAT）与 verifier.py（独立判定）各自实现。
两边都 import 本模块不构成「共享约束逻辑」。
"""
from pathlib import Path
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel, Field

RULE_TYPES = frozenset({
    'forbid_slots', 'pin_window', 'daily_min', 'daily_max', 'weekday_exact',
    'consecutive', 'spacing', 'alternate_weeks', 'venue_capacity',
    'preferred_periods', 'avoid_after', 'teacher_balance',
})

# 可放松 = L2 无解诊断时值得挂 assumption 的规则
RELAXABLE = frozenset({
    'daily_min', 'daily_max', 'weekday_exact', 'consecutive', 'spacing',
    'preferred_periods', 'avoid_after', 'teacher_balance',
})

SCOPE_DIMS = ('grade', 'family', 'course', 'teacher', 'class')


class RuleError(ValueError):
    """规则声明有误。"""


class Rule(BaseModel):
    type: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    mode: str = 'hard'
    enabled: bool = True
    weight: int = 0

    def validate_type(self) -> 'Rule':
        if self.type not in RULE_TYPES:
            raise RuleError('未知规则类型 %r，已知类型：%s'
                            % (self.type, sorted(RULE_TYPES)))
        for dim in self.scope:
            if dim not in SCOPE_DIMS:
                raise RuleError('未知作用域维度 %r，仅支持 %s' % (dim, list(SCOPE_DIMS)))
        return self

    @property
    def relaxable(self) -> bool:
        return self.type in RELAXABLE


def _task_dim(task, dim, cfg):
    if dim == 'grade':
        return task.grade
    if dim == 'course':
        return task.course
    if dim == 'family':
        return cfg.family_of(task.course)
    if dim == 'teacher':
        return task.teacher
    if dim == 'class':
        return task.class_id
    raise RuleError('未知作用域维度 %r，仅支持 %s' % (dim, list(SCOPE_DIMS)))


def matches(rule: Rule, task, cfg) -> bool:
    for dim, want in rule.scope.items():
        if want is None or want == '*':
            continue
        have = _task_dim(task, dim, cfg)
        wanted = want if isinstance(want, (list, tuple, set)) else [want]
        if have not in wanted:
            return False
    return True


def select_tasks(rule: Rule, tasks, cfg) -> List:
    return [t for t in tasks if matches(rule, t, cfg)]


def load_rules(*paths) -> List[Rule]:
    rules: List[Rule] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        for raw in (data.get('rules') or []):
            rules.append(Rule(**raw).validate_type())
    return rules


_SCOPE_LABEL = {'grade': '年级', 'family': '学科系', 'course': '课程',
                'teacher': '教师', 'class': '班级'}

_TYPE_TEMPLATE = {
    'forbid_slots': '禁排 {slots_n} 个时段',
    'pin_window': '锁定在 {slots_n} 个时段构成的窗口内',
    'daily_min': '每天至少 {n} 节',
    'daily_max': '每天至多 {n} 节',
    'weekday_exact': '{weekdays} 各 {n} 节',
    'consecutive': '有 {days} 天连堂 {length} 节',
    'spacing': '同教师两班之间至少隔 {min_gap} 节',
    'alternate_weeks': '{pair} 单双周轮换共用同一格',
    'venue_capacity': '场地 {venue} 同时最多 {capacity} 个班',
}


def describe(rule: Rule) -> str:
    scope_text = '、'.join(
        '%s=%s' % (_SCOPE_LABEL.get(d, d), v) for d, v in rule.scope.items()) or '全局'
    params = dict(rule.params)
    params['slots_n'] = len(params.get('slots', []))
    template = _TYPE_TEMPLATE.get(rule.type, rule.type + ' {}')
    try:
        body = template.format(**params)
    except (KeyError, IndexError):
        body = '%s %s' % (rule.type, rule.params)
    return '[%s] %s' % (scope_text, body)
