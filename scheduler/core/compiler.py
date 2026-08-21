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
