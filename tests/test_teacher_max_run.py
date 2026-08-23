"""teacher_max_run 软约束：编译器最小化 + 校验器独立计数。"""
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from scheduler.core import calendar as cal
from scheduler.core.compiler import compile_model
from scheduler.core.config import load_config
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.rules import Rule
from scheduler.core.solver import Placement, Solution
from scheduler.core.verifier import verify_soft

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def make_dataset(tasks):
    names = {t.teacher for t in tasks}
    return Dataset(grade='初三',
                   classes=sorted({t.class_id for t in tasks}),
                   teachers={n: Teacher(name=n) for n in names},
                   tasks=tasks)


def _solve(compiled, seconds=10):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 8
    return solver, solver.Solve(compiled.model)


def _placements(solver, compiled, dataset):
    by_id = {t.id: t for t in dataset.tasks}
    return [Placement(task_id=tid, class_id=by_id[tid].class_id,
                      course=by_id[tid].course, teacher=by_id[tid].teacher,
                      slot=s, parity=by_id[tid].parity)
            for (tid, s), v in compiled.x.items() if solver.Value(v)]


def _rule():
    return Rule(type='teacher_max_run', scope={'grade': '初三'},
                params={'max_len': 2}, mode='soft', weight=10)


def test_soft_rule_drives_to_zero_when_spreadable(cfg):
    """3 个班各 1 节、同一位教师：可分散时软约束应驱使 0 处三连堂。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='音乐',
                          teacher='王老师', periods=1) for i in range(3)]
    ds = make_dataset(tasks)
    compiled = compile_model(ds, cfg, [_rule()])
    assert compiled.soft_terms, '应产出惩罚项'
    solver, status = _solve(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    sol = Solution(status='OPTIMAL', wall_time=0, placements=_placements(solver, compiled, ds))
    assert verify_soft(sol, ds, cfg, [_rule()]) == []


def test_verifier_counts_a_weekly_three_run_once(cfg):
    """周课三连堂在单双两周都上课，校验器只报 1 处（标「每周」）。"""
    ds = make_dataset([TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                                    teacher='王老师', periods=1) for i in range(3)])
    sol = Solution(status='OPTIMAL', wall_time=0, placements=[
        Placement(task_id=0, class_id=1, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 1)),
        Placement(task_id=1, class_id=2, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 2)),
        Placement(task_id=2, class_id=3, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 3)),
    ])
    out = verify_soft(sol, ds, cfg, [_rule()])
    assert len(out) == 1
    assert '（每周）' in out[0].detail
    assert '连续 3 节' in out[0].detail


def test_verifier_counts_a_single_week_three_run(cfg):
    """单周课三连堂只在单周报，标「单周」。"""
    ds = make_dataset([TeachingTask(id=i, grade='初三', class_id=i + 1, course='美术',
                                    teacher='王老师', periods=1, parity='单周')
                       for i in range(3)])
    sol = Solution(status='OPTIMAL', wall_time=0, placements=[
        Placement(task_id=0, class_id=1, course='美术', teacher='王老师',
                  slot=cal.slot_index(0, 6), parity='单周'),
        Placement(task_id=1, class_id=2, course='美术', teacher='王老师',
                  slot=cal.slot_index(0, 7), parity='单周'),
        Placement(task_id=2, class_id=3, course='美术', teacher='王老师',
                  slot=cal.slot_index(0, 8), parity='单周'),
    ])
    out = verify_soft(sol, ds, cfg, [_rule()])
    assert len(out) == 1
    assert '（单周）' in out[0].detail


def test_four_in_a_row_counts_as_one_maximal_run(cfg):
    """4 连堂是一段，校验器报 1 处、长度 4（不报两个 3-窗口）。"""
    ds = make_dataset([TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                                    teacher='王老师', periods=1) for i in range(4)])
    sol = Solution(status='OPTIMAL', wall_time=0, placements=[
        Placement(task_id=i, class_id=i + 1, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 1 + i)) for i in range(4)
    ])
    out = verify_soft(sol, ds, cfg, [_rule()])
    assert len(out) == 1
    assert '连续 4 节' in out[0].detail


def test_two_in_a_row_is_not_a_violation(cfg):
    """2 连堂（语文连堂规则要求的）不触发——max_len=2 允许。"""
    ds = make_dataset([TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                                    teacher='王老师', periods=1) for i in range(2)])
    sol = Solution(status='OPTIMAL', wall_time=0, placements=[
        Placement(task_id=0, class_id=1, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 1)),
        Placement(task_id=1, class_id=2, course='语文', teacher='王老师',
                  slot=cal.slot_index(0, 2)),
    ])
    assert verify_soft(sol, ds, cfg, [_rule()]) == []


def test_unknown_soft_rule_still_skipped(cfg):
    """没有处理器的软规则（如 spacing）仍进 skipped_soft，不影响目标。"""
    ds = make_dataset([TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                                    teacher='A', periods=1)])
    soft = Rule(type='spacing', scope={'grade': '初三'}, params={'min_gap': 1},
                mode='soft', weight=5)
    compiled = compile_model(ds, cfg, [soft])
    assert compiled.skipped_soft == [soft]
    assert compiled.soft_terms == []
