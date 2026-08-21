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
    solver.parameters.max_time_in_seconds = 10
    return solver, solver.Solve(compiled.model)


def slots_of(solver, compiled, task_id):
    return {cal.slot_of(s) for s in range(cal.N_SLOTS)
            if solver.Value(compiled.x[(task_id, s)])}


def test_forbid_slots_blocks_those_slots(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=40)
    rule = Rule(type='forbid_slots', scope={'teacher': '李琼'},
                params={'slots': [[0, 4], [0, 5], [4, 1], [4, 2], [4, 3]]})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    placed = slots_of(solver, compiled, 0)
    assert placed.isdisjoint({(0, 4), (0, 5), (4, 1), (4, 2), (4, 3)})


def test_forbid_slots_applies_to_all_courses_of_that_teacher(cfg):
    """陈芬周四下午开会 —— 她的综实1 也不能排在那里。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='物理', teacher='陈芬', periods=4),
        TeachingTask(id=1, grade='初三', class_id=1, course='综实1', teacher='陈芬', periods=1),
    ]
    rule = Rule(type='forbid_slots', scope={'teacher': '陈芬'},
                params={'slots': [[3, p] for p in (6, 7, 8, 9)]})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, _ = run(compiled)
    for task_id in (0, 1):
        assert slots_of(solver, compiled, task_id).isdisjoint({(3, 6), (3, 7), (3, 8), (3, 9)})


def test_forbid_slots_can_make_infeasible(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=43)
    rule = Rule(type='forbid_slots', scope={'teacher': '李琼'},
                params={'slots': [[0, p] for p in range(1, 10)]})   # 封掉周一 9 格
    _, status = run(compile_model(ds([task]), cfg, [rule]))
    assert status == cp_model.INFEASIBLE     # 43 节要塞进 36 格


def test_pin_window_confines_task_to_window(cfg):
    """体比周课时 1，窗口周二 8、9 节 —— 落在窗口内任一格都合法。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='体比',
                        teacher='周志宁', periods=1)
    rule = Rule(type='pin_window', scope={'course': '体比'},
                params={'slots': [[1, 8], [1, 9]]})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, status = run(compiled)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert slots_of(solver, compiled, 0) <= {(1, 8), (1, 9)}


def test_pin_window_of_size_one_is_exact(cfg):
    """班会：周一第9节，窗口恰好等于课时，退化为钉死。"""
    task = TeachingTask(id=0, grade='初三', class_id=1, course='班会',
                        teacher='李琼', periods=1)
    rule = Rule(type='pin_window', scope={'course': '班会'}, params={'slots': [[0, 9]]})
    compiled = compile_model(ds([task]), cfg, [rule])
    solver, _ = run(compiled)
    assert slots_of(solver, compiled, 0) == {(0, 9)}


def test_pin_window_too_small_is_infeasible(cfg):
    task = TeachingTask(id=0, grade='初三', class_id=1, course='体比',
                        teacher='周志宁', periods=3)
    rule = Rule(type='pin_window', scope={'course': '体比'},
                params={'slots': [[1, 8], [1, 9]]})
    _, status = run(compile_model(ds([task]), cfg, [rule]))
    assert status == cp_model.INFEASIBLE


def test_pin_window_only_hits_scoped_course(cfg):
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='班会', teacher='李琼', periods=1),
        TeachingTask(id=1, grade='初三', class_id=1, course='语文', teacher='李琼', periods=6),
    ]
    rule = Rule(type='pin_window', scope={'course': '班会'}, params={'slots': [[0, 9]]})
    compiled = compile_model(ds(tasks), cfg, [rule])
    solver, _ = run(compiled)
    assert slots_of(solver, compiled, 0) == {(0, 9)}
    assert len(slots_of(solver, compiled, 1)) == 6
