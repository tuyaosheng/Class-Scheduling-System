from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from scheduler.core import calendar as cal
from scheduler.core.compiler import compile_model, active_in
from scheduler.core.config import load_config
from scheduler.core.models import Dataset, Teacher, TeachingTask

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def make_dataset(tasks, teachers=None):
    names = {t.teacher for t in tasks}
    return Dataset(grade='初三',
                   classes=sorted({t.class_id for t in tasks}),
                   teachers=teachers or {n: Teacher(name=n) for n in names},
                   tasks=tasks)


def solve(compiled):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10
    return solver, solver.Solve(compiled.model)


def placed_slots(solver, compiled, task_id):
    return sorted(s for s in range(cal.N_SLOTS)
                  if solver.Value(compiled.x[(task_id, s)]))


def test_active_in():
    t = TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='A', periods=1)
    assert active_in(t, '单周') and active_in(t, '双周')
    art = t.model_copy(update={'course': '美术', 'parity': '单周'})
    assert active_in(art, '单周') and not active_in(art, '双周')


def test_each_task_gets_exactly_its_periods(cfg):
    ds = make_dataset([TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                                    teacher='李琼', periods=6)])
    compiled = compile_model(ds, cfg, [])
    solver, status = solve(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert len(placed_slots(solver, compiled, 0)) == 6


def test_class_cannot_have_two_courses_in_one_slot(cfg):
    """一个班 45 格塞 46 节课必须无解。"""
    ds = make_dataset([
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='A', periods=23),
        TeachingTask(id=1, grade='初三', class_id=1, course='数学', teacher='B', periods=23),
    ])
    solver, status = solve(compile_model(ds, cfg, []))
    assert status == cp_model.INFEASIBLE


def test_teacher_cannot_be_in_two_classes_at_once(cfg):
    """一位教师两个班各 23 节，共 46 > 45 格，必须无解。"""
    ds = make_dataset([
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='李琼', periods=23),
        TeachingTask(id=1, grade='初三', class_id=2, course='语文', teacher='李琼', periods=23),
    ])
    solver, status = solve(compile_model(ds, cfg, []))
    assert status == cp_model.INFEASIBLE


def test_multi_class_course_exempts_teacher_clash(cfg):
    """体比是合班课：周志宁同一格面向 3 个班，不算分身。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=c, course='体比',
                          teacher='周志宁', periods=45)
             for i, c in enumerate([1, 2, 25])]
    solver, status = solve(compile_model(make_dataset(tasks), cfg, []))
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_non_multi_class_course_still_clashes(cfg):
    """同样的 3 个班换成体育（非合班）就必须无解。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=c, course='体育',
                          teacher='周志宁', periods=45)
             for i, c in enumerate([1, 2, 25])]
    solver, status = solve(compile_model(make_dataset(tasks), cfg, []))
    assert status == cp_model.INFEASIBLE


def test_odd_and_even_week_tasks_may_share_a_slot(cfg):
    """美术（单周）与心理（双周）占同一格，两位不同教师，不构成冲突。

    这里把两门课都撑满 45 格 —— 只有按周次分组建模才可能有解。
    """
    ds = make_dataset([
        TeachingTask(id=0, grade='初三', class_id=1, course='美术',
                     teacher='梁艳红', periods=45, parity='单周'),
        TeachingTask(id=1, grade='初三', class_id=1, course='心理',
                     teacher='郭泽琪', periods=45, parity='双周'),
    ])
    solver, status = solve(compile_model(ds, cfg, []))
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_same_parity_tasks_still_clash(cfg):
    """两门都是单周就不能共格。"""
    ds = make_dataset([
        TeachingTask(id=0, grade='初三', class_id=1, course='美术',
                     teacher='梁艳红', periods=45, parity='单周'),
        TeachingTask(id=1, grade='初三', class_id=1, course='美术',
                     teacher='胡美玲', periods=45, parity='单周'),
    ])
    solver, status = solve(compile_model(ds, cfg, []))
    assert status == cp_model.INFEASIBLE


def test_variable_count_matches_tasks_times_slots(cfg):
    ds = make_dataset([TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                                    teacher='T%d' % i, periods=1) for i in range(10)])
    compiled = compile_model(ds, cfg, [])
    assert len(compiled.x) == 10 * cal.N_SLOTS


def test_soft_rules_are_skipped_in_m2(cfg):
    from scheduler.core.rules import Rule
    ds = make_dataset([TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                                    teacher='A', periods=1)])
    soft = Rule(type='spacing', scope={'grade': '初三'}, params={'min_gap': 1},
                mode='soft', weight=5)
    compiled = compile_model(ds, cfg, [soft])
    assert compiled.skipped_soft == [soft]


def test_disabled_rules_are_ignored(cfg):
    from scheduler.core.rules import Rule
    ds = make_dataset([TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                                    teacher='A', periods=1)])
    off = Rule(type='daily_min', scope={'grade': '初三'}, params={'n': 9}, enabled=False)
    solver, status = solve(compile_model(ds, cfg, [off]))
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
