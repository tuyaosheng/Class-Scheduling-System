from pathlib import Path

import pytest

from scheduler.core.config import load_config
from scheduler.core.diagnose import format_conflict, minimal_conflict
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


def test_feasible_model_yields_no_conflict(cfg):
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                          teacher='李琼', periods=6)]
    rule = Rule(type='daily_min', scope={'family': '语文'}, params={'n': 1})
    conflict = minimal_conflict(ds(tasks), cfg, [rule], max_seconds=15)
    assert conflict.status in ('OPTIMAL', 'FEASIBLE')
    assert conflict.rules == []


def test_conflicting_daily_rules_are_returned(cfg):
    """每天至少 2 节（共需 10 节）与每天至多 1 节（最多 5 节）直接矛盾。"""
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                          teacher='李琼', periods=6)]
    rules = [
        Rule(type='daily_min', scope={'family': '语文'}, params={'n': 2}),
        Rule(type='daily_max', scope={'family': '语文'}, params={'n': 1}),
    ]
    conflict = minimal_conflict(ds(tasks), cfg, rules, max_seconds=15)
    assert conflict.status == 'INFEASIBLE'
    assert conflict.rules, '应返回非空冲突集'
    text = ' '.join(conflict.rules)
    assert '每天至少' in text and '每天至多' in text


def test_conflict_set_is_minimal(cfg):
    """无关规则不该出现在冲突集里。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='李琼', periods=6),
        TeachingTask(id=1, grade='初三', class_id=1, course='历史', teacher='张三', periods=3),
    ]
    rules = [
        Rule(type='daily_min', scope={'family': '语文'}, params={'n': 2}),
        Rule(type='daily_max', scope={'family': '语文'}, params={'n': 1}),
        Rule(type='daily_max', scope={'family': '历史'}, params={'n': 1}),   # 无关
    ]
    conflict = minimal_conflict(ds(tasks), cfg, rules, max_seconds=15)
    assert conflict.status == 'INFEASIBLE'
    assert '历史' not in ' '.join(conflict.rules)


def test_non_relaxable_rules_never_appear(cfg):
    """pin_window 造成的无解不挂 assumption，冲突集应为空但状态仍是 INFEASIBLE。"""
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='体比',
                          teacher='周志宁', periods=3)]
    rules = [Rule(type='pin_window', scope={'course': '体比'},
                  params={'slots': [[1, 8], [1, 9]]})]
    conflict = minimal_conflict(ds(tasks), cfg, rules, max_seconds=15)
    assert conflict.status == 'INFEASIBLE'
    assert conflict.rules == []


def test_format_conflict_readable(cfg):
    from scheduler.core.diagnose import Conflict
    text = format_conflict(Conflict(status='INFEASIBLE',
                                    rules=['[学科系=语文] 每天至少 2 节',
                                           '[学科系=语文] 每天至多 1 节']))
    assert '冲突集' in text and '每天至少 2 节' in text


def test_cli_solve_stops_at_precheck(tmp_path, monkeypatch, capsys):
    """预检有问题时不该进求解器。"""
    from scheduler.cli import main
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    bad_rules = tmp_path / 'rules.yaml'
    bad_rules.write_text(
        'rules:\n'
        '  - {type: daily_min, scope: {grade: 初三, family: 化学}, params: {n: 2}, mode: hard}\n',
        encoding='utf-8')
    # 复制其余配置到 tmp_path
    import shutil
    for name in ('calendar.yaml', 'courses.yaml', 'plans.yaml', 'venues.yaml',
                 'rules.generated.yaml'):
        shutil.copy(root / 'scheduler' / 'config' / name, tmp_path / name)
    code = main(['solve', '--config-dir', str(tmp_path),
                 '--out', str(tmp_path / 'x.xlsx'), '--max-seconds', '10'])
    out = capsys.readouterr().out
    assert code == 2
    assert '规则自相矛盾' in out
    assert '化学' in out
