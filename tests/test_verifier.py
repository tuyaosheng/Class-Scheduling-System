from pathlib import Path

import pytest

from scheduler.core import calendar as cal
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel
from scheduler.core.rules import Rule, load_rules
from scheduler.core.solver import Placement, Solution, solve
from scheduler.core.verifier import verify

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'
EXCEL = ROOT / '任课与排课说明.xlsx'


def test_verifier_does_not_import_compiler():
    """结构性守卫：两边共享约束逻辑就失去了互相证伪的能力。"""
    import ast
    src = (ROOT / 'scheduler' / 'core' / 'verifier.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any('compiler' in m for m in imported), \
        'verifier.py 不得 import compiler，实际导入：%s' % sorted(imported)


@pytest.fixture(scope='module')
def real():
    cfg = load_config(CONFIG_DIR)
    result = import_excel(EXCEL, cfg, grade='初三')
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    solution = solve(result.dataset, cfg, rules, max_seconds=30)
    return cfg, result.dataset, rules, solution


def test_real_solution_has_zero_violations(real):
    cfg, dataset, rules, solution = real
    assert solution.feasible
    violations = verify(solution, dataset, cfg, rules)
    assert violations == [], '\n'.join(v.detail for v in violations)


def kinds(violations):
    return {v.kind for v in violations}


def tamper(solution, task_id, old_slot, new_slot):
    """复制一份解，把 (task_id, old_slot) 这一节课挪到 new_slot。"""
    placements = [p.model_copy() for p in solution.placements]
    for p in placements:
        if p.task_id == task_id and p.slot == old_slot:
            p.slot = new_slot
            break
    return Solution(status=solution.status, wall_time=0.0, placements=placements)


def test_detects_class_double_booking(real):
    cfg, dataset, rules, solution = real
    ones = [p for p in solution.placements if p.class_id == 1 and p.parity is None]
    victim, other = ones[0], ones[1]
    broken = tamper(solution, victim.task_id, victim.slot, other.slot)
    assert '班级重课' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_pin_window_violation(real):
    cfg, dataset, rules, solution = real
    victim = next(p for p in solution.placements if p.course == '班会' and p.class_id == 1)
    broken = tamper(solution, victim.task_id, victim.slot, cal.slot_index(2, 3))
    assert '越出窗口' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_forbidden_slot_violation(real):
    cfg, dataset, rules, solution = real
    # 陈芬周四下午开会
    victim = next(p for p in solution.placements
                  if p.teacher == '陈芬' and p.course == '物理')
    broken = tamper(solution, victim.task_id, victim.slot, cal.slot_index(3, 7))
    assert '违反禁排' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_missing_daily_min(real):
    cfg, dataset, rules, solution = real
    # 把 1 班某天唯一的物理系课程挪到别的一天
    target_day = 2
    victim = next(p for p in solution.placements
                  if p.class_id == 1 and cfg.family_of(p.course) == '物理'
                  and cal.slot_of(p.slot)[0] == target_day)
    broken = tamper(solution, victim.task_id, victim.slot, cal.slot_index(0, 1))
    assert '每日下限不足' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_alternate_not_sharing_slot(real):
    cfg, dataset, rules, solution = real
    psy = next(p for p in solution.placements if p.course == '心理' and p.class_id == 1)
    broken = tamper(solution, psy.task_id, psy.slot, (psy.slot + 1) % cal.N_SLOTS)
    assert '单双周未共格' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_wrong_period_count(real):
    cfg, dataset, rules, solution = real
    placements = [p for p in solution.placements
                  if not (p.class_id == 1 and p.course == '语文')][:]
    broken = Solution(status='FEASIBLE', wall_time=0.0, placements=placements)
    assert '课时数不符' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_teacher_clash_but_not_for_multi_class(real):
    """体比是合班课：同教师同格多个班合法，不该报违规。"""
    cfg, dataset, rules, solution = real
    tibi = [p for p in solution.placements if p.course == '体比' and p.teacher == '周志宁']
    assert len(tibi) >= 2
    placements = [p.model_copy() for p in solution.placements]
    target = tibi[0].slot
    for p in placements:
        if p.course == '体比' and p.teacher == '周志宁':
            p.slot = target
    broken = Solution(status='FEASIBLE', wall_time=0.0, placements=placements)
    assert '教师分身' not in kinds(verify(broken, dataset, cfg, rules))


def test_detects_venue_overflow():
    """3 间物理实验室，4 个班同格上综实1 应报超容。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    cfg = load_config(CONFIG_DIR)
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='综实1',
                          teacher='T%d' % i, periods=1) for i in range(4)]
    dataset = Dataset(grade='初三', classes=[1, 2, 3, 4],
                      teachers={t.teacher: Teacher(name=t.teacher) for t in tasks},
                      tasks=tasks)
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=t.id, class_id=t.class_id, course='综实1',
                  teacher=t.teacher, slot=0) for t in tasks])
    assert '场地超容' in kinds(verify(solution, dataset, cfg, []))
