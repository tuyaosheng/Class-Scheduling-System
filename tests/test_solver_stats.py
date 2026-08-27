"""solve()/solve_many() 暴露的 objective/stats——求解监控面板的数据来源。

objective 只在模型有软约束（soft_terms 非空）时才有意义，纯硬约束模型没有
Minimize 目标；stats 是 CP-SAT 的 ResponseStats() 原文，任何一次 Solve() 后
都有意义，用来证明"求解器真的做了工作"，不是伪造的动画（见 CLAUDE.md
「关于看到程序怎么算」）。
"""
from pathlib import Path

import pytest

from scheduler.core.config import load_config
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.rules import Rule
from scheduler.core.solver import solve, solve_many

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def _make_dataset(tasks):
    names = {t.teacher for t in tasks}
    return Dataset(grade='初三', classes=sorted({t.class_id for t in tasks}),
                   teachers={n: Teacher(name=n) for n in names}, tasks=tasks)


def _soft_rule():
    return Rule(type='teacher_max_run', scope={'grade': '初三'},
               params={'max_len': 2}, mode='soft', weight=10)


def test_objective_is_none_for_a_purely_hard_model(cfg):
    ds = _make_dataset([TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                                     teacher='张老师', periods=1)])
    sol = solve(ds, cfg, [])
    assert sol.feasible
    assert sol.objective is None
    assert sol.stats


def test_objective_is_set_when_a_soft_rule_is_active(cfg):
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='音乐',
                          teacher='王老师', periods=1) for i in range(3)]
    ds = _make_dataset(tasks)
    sol = solve(ds, cfg, [_soft_rule()])
    assert sol.feasible
    assert sol.objective is not None
    assert sol.stats


def test_solve_many_populates_objective_and_stats_per_candidate(cfg):
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='音乐',
                          teacher='王老师', periods=1) for i in range(3)]
    ds = _make_dataset(tasks)
    solutions = solve_many(ds, cfg, [_soft_rule()], count=2, min_diff=1)
    assert len(solutions) >= 1
    for sol in solutions:
        assert sol.objective is not None
        assert sol.stats
