from collections import Counter
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from scheduler.core import calendar as cal
from scheduler.core.compiler import compile_model
from scheduler.core.config import load_config
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.rules import Rule

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def ds(tasks):
    return Dataset(grade='初三', classes=sorted({t.class_id for t in tasks}),
                   teachers={t.teacher: Teacher(name=t.teacher) for t in tasks},
                   tasks=tasks)


def run(compiled):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15
    return solver, solver.Solve(compiled.model)


def per_day(solver, compiled, task_ids):
    counts = Counter()
    for task_id in task_ids:
        for s in range(cal.N_SLOTS):
            if solver.Value(compiled.x[(task_id, s)]):
                counts[cal.slot_of(s)[0]] += 1
    return counts


def test_daily_min_one_per_day(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=6)
    rule = Rule(type='daily_min', scope={'family': '语文'}, params={'n': 1})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    counts = per_day(solver, compiled, [0])
    assert all(counts[d] >= 1 for d in range(5))


def test_daily_min_counts_the_whole_family(cfg):
    """物理 4 节独自撑不起「每天 1 节」，加上综实1 的 1 节才行 —— 学科系的全部意义。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='物理', teacher='陈芬', periods=4),
        TeachingTask(id=1, grade='初三', class_id=1, course='综实1', teacher='陈芬', periods=1),
    ]
    rule = Rule(type='daily_min', scope={'family': '物理'}, params={'n': 1})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    counts = per_day(solver, compiled, [0, 1])
    assert all(counts[d] >= 1 for d in range(5))


def test_daily_min_by_course_name_is_infeasible(cfg):
    """反证：把同一条规则的作用域从 family 改成 course，立刻无解。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='物理', teacher='陈芬', periods=4),
        TeachingTask(id=1, grade='初三', class_id=1, course='综实1', teacher='陈芬', periods=1),
    ]
    rule = Rule(type='daily_min', scope={'course': '物理'}, params={'n': 1})
    _, status = run(compile_model(ds(tasks), cfg, [rule]))
    assert status == cp_model.INFEASIBLE


def test_daily_max_one_per_day(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='化学',
                        teacher='王林', periods=4)
    rule = Rule(type='daily_max', scope={'family': '化学'}, params={'n': 1})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert all(v <= 1 for v in per_day(solver, compiled, [0]).values())


def test_daily_max_infeasible_when_over_capacity(cfg):
    """6 节课要求每天最多 1 节，只有 5 天，必然无解。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='化学',
                        teacher='王林', periods=6)
    rule = Rule(type='daily_max', scope={'family': '化学'}, params={'n': 1})
    _, status = run(compile_model(ds([task]), cfg, [rule]))
    assert status == cp_model.INFEASIBLE


def test_daily_rules_are_per_class(cfg):
    """两个班各自满足每天 1 节，不能互相顶替。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                          teacher='T%d' % i, periods=5) for i in range(2)]
    rule = Rule(type='daily_min', scope={'family': '语文'}, params={'n': 1})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    for task_id in (0, 1):
        counts = per_day(solver, compiled, [task_id])
        assert all(counts[d] == 1 for d in range(5))


def test_weekday_exact_pe(cfg):
    """体育 3 节，周一三四各恰好 1 节。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='体育',
                        teacher='周志宁', periods=3)
    rule = Rule(type='weekday_exact', scope={'family': '体育'},
                params={'weekdays': ['周一', '周三', '周四'], 'n': 1})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    counts = per_day(solver, compiled, [0])
    assert counts[0] == counts[2] == counts[3] == 1
    assert counts[1] == counts[4] == 0


def test_weekday_exact_ignores_days_not_listed(cfg):
    """体比钉在周二，不受「周一三四各 1 节」约束干扰。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='体育', teacher='周志宁', periods=3),
        TeachingTask(id=1, grade='初三', class_id=1, course='体比', teacher='周志宁', periods=1),
    ]
    rules = [
        Rule(type='weekday_exact', scope={'family': '体育'},
             params={'weekdays': ['周一', '周三', '周四'], 'n': 1}),
        Rule(type='pin_window', scope={'course': '体比'}, params={'slots': [[1, 8], [1, 9]]}),
    ]
    compiled = compile_model(ds(tasks), cfg, rules)
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    counts = per_day(solver, compiled, [0, 1])
    assert counts[0] == counts[2] == counts[3] == 1
    assert counts[1] == 1          # 体比落在周二


def test_assumptions_are_registered_when_requested(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=6)
    rule = Rule(type='daily_min', scope={'family': '语文'}, params={'n': 1})
    compiled = compile_model(ds([task]), cfg, [rule], with_assumptions=True)
    assert len(compiled.assumptions) == 5      # 每天一条
    assert all(r is rule for r in compiled.assumptions.values())


def test_no_assumptions_by_default(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=6)
    rule = Rule(type='daily_min', scope={'family': '语文'}, params={'n': 1})
    assert compile_model(ds([task]), cfg, [rule]).assumptions == {}
