from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from scheduler.core import calendar as cal
from scheduler.core.compiler import adjacent_pairs, compile_model
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


def slots_of(solver, compiled, task_id):
    return sorted(s for s in range(cal.N_SLOTS) if solver.Value(compiled.x[(task_id, s)]))


def test_adjacent_pairs_excludes_lunch_break():
    pairs = adjacent_pairs()
    assert (4, 5) in pairs and (5, 6) not in pairs   # 第5节与第6节跨午休
    assert (6, 7) in pairs and (8, 9) in pairs
    assert len(pairs) == 7                            # 每天 7 对


def test_alternate_binds_art_and_psych_to_same_slot(cfg):
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='美术',
                     teacher='梁艳红', periods=1, parity='单周'),
        TeachingTask(id=1, grade='初三', class_id=1, course='心理',
                     teacher='郭泽琪', periods=1, parity='双周'),
    ]
    rule = Rule(type='alternate_weeks', scope={'grade': '初三'},
                params={'pair': ['美术', '心理']})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert slots_of(solver, compiled, 0) == slots_of(solver, compiled, 1)


def test_alternate_is_per_class_not_global(cfg):
    """1班的美术与2班的心理不该被绑在一起。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='美术',
                     teacher='梁艳红', periods=1, parity='单周'),
        TeachingTask(id=1, grade='初三', class_id=1, course='心理',
                     teacher='郭泽琪', periods=1, parity='双周'),
        TeachingTask(id=2, grade='初三', class_id=2, course='美术',
                     teacher='梁艳红', periods=1, parity='单周'),
        TeachingTask(id=3, grade='初三', class_id=2, course='心理',
                     teacher='郭泽琪', periods=1, parity='双周'),
    ]
    rule = Rule(type='alternate_weeks', scope={'grade': '初三'},
                params={'pair': ['美术', '心理']})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert slots_of(solver, compiled, 0) == slots_of(solver, compiled, 1)
    assert slots_of(solver, compiled, 2) == slots_of(solver, compiled, 3)
    # 梁艳红同为两班的美术老师，两班必须错开
    assert slots_of(solver, compiled, 0) != slots_of(solver, compiled, 2)


def test_alternate_skips_class_missing_one_side(cfg):
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='美术',
                          teacher='梁艳红', periods=1, parity='单周')]
    rule = Rule(type='alternate_weeks', scope={'grade': '初三'},
                params={'pair': ['美术', '心理']})
    _, status = run(compile_model(ds(tasks), cfg, [rule]))
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_consecutive_produces_a_double_period(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=6)
    rule = Rule(type='consecutive', scope={'course': '语文'},
                params={'days': 1, 'length': 2})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    placed = set(slots_of(solver, compiled, 0))
    has_double = any(s in placed and s + 1 in placed
                     and cal.slot_of(s)[0] == cal.slot_of(s + 1)[0]
                     and (cal.slot_of(s)[1], cal.slot_of(s + 1)[1]) in adjacent_pairs()
                     for s in placed)
    assert has_double


def test_consecutive_infeasible_when_forced_apart(cfg):
    """只给周一 1、3、5 三格（互不相邻），连堂无处安放。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=3)
    rules = [
        Rule(type='pin_window', scope={'course': '语文'},
             params={'slots': [[0, 1], [0, 3], [0, 5]]}),
        Rule(type='consecutive', scope={'course': '语文'},
             params={'days': 1, 'length': 2}),
    ]
    _, status = run(compile_model(ds([task]), cfg, rules))
    assert status == cp_model.INFEASIBLE


def test_consecutive_does_not_count_across_lunch(cfg):
    """只给周一第 5、6 节 —— 跨午休不算连堂。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=2)
    rules = [
        Rule(type='pin_window', scope={'course': '语文'},
             params={'slots': [[0, 5], [0, 6]]}),
        Rule(type='consecutive', scope={'course': '语文'},
             params={'days': 1, 'length': 2}),
    ]
    _, status = run(compile_model(ds([task]), cfg, rules))
    assert status == cp_model.INFEASIBLE
