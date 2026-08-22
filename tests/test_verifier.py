from collections import defaultdict
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
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                # `from . import X` —— 模块名在 alias 里，module 为 None
                imported.update(alias.name for alias in node.names)
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


# ---------------------------------------------------------------- C1：合班 session

def test_multi_class_session_still_clashes_with_the_teachers_other_class():
    """合班课折叠成一节，但仍占用教师 —— 与其常规课同格就是分身。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    cfg = load_config(CONFIG_DIR)
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='体育', teacher='王老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=2, course='体比', teacher='王老师', periods=1),
    ]
    dataset = Dataset(grade='初三', classes=[1, 2],
                      teachers={'王老师': Teacher(name='王老师')}, tasks=tasks)
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=0, class_id=1, course='体育', teacher='王老师', slot=0),
        Placement(task_id=1, class_id=2, course='体比', teacher='王老师', slot=0),
    ])
    violations = verify(solution, dataset, cfg, [])
    assert '教师分身' in kinds(violations)
    assert any('体比' in v.detail and '体育' in v.detail for v in violations)


def test_multi_class_session_spread_over_two_slots_is_not_a_clash():
    """合班 session 不强制同格：3 个班的体比分落 T8/T9 仍然合法。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    cfg = load_config(CONFIG_DIR)
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='体比',
                          teacher='王老师', periods=1) for i in range(3)]
    dataset = Dataset(grade='初三', classes=[1, 2, 3],
                      teachers={'王老师': Teacher(name='王老师')}, tasks=tasks)
    slots = [cal.slot_index(1, 8), cal.slot_index(1, 8), cal.slot_index(1, 9)]
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=t.id, class_id=t.class_id, course='体比',
                  teacher='王老师', slot=s) for t, s in zip(tasks, slots)])
    assert verify(solution, dataset, cfg, []) == []


def test_two_different_multi_class_courses_are_two_sessions():
    """体比与体选是两个 session，同格即分身。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    cfg = load_config(CONFIG_DIR)
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='体比', teacher='王老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=2, course='体选', teacher='王老师', periods=1),
    ]
    dataset = Dataset(grade='初三', classes=[1, 2],
                      teachers={'王老师': Teacher(name='王老师')}, tasks=tasks)
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=0, class_id=1, course='体比', teacher='王老师', slot=0),
        Placement(task_id=1, class_id=2, course='体选', teacher='王老师', slot=0),
    ])
    assert '教师分身' in kinds(verify(solution, dataset, cfg, []))


def test_venue_counts_multi_class_session_once():
    """8 个班的体比在操场上只是 1 处占用，容量 1 不该报超容。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    from scheduler.core.rules import Rule
    cfg = load_config(CONFIG_DIR)
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='体比',
                          teacher='王老师', periods=1) for i in range(8)]
    dataset = Dataset(grade='初三', classes=[t.class_id for t in tasks],
                      teachers={'王老师': Teacher(name='王老师')}, tasks=tasks)
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=t.id, class_id=t.class_id, course='体比',
                  teacher='王老师', slot=0) for t in tasks])
    rule = Rule(type='venue_capacity', scope={},
                params={'venue': '操场', 'capacity': 1})
    assert verify(solution, dataset, cfg, [rule]) == []


def test_venue_capacity_rule_detects_two_sessions_over_capacity():
    """反证：两位教师各带一门操场合班课，同格就是 2 处占用，容量 1 报超容。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    from scheduler.core.rules import Rule
    cfg = load_config(CONFIG_DIR)
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='体比', teacher='王老师', periods=1),
        TeachingTask(id=1, grade='初三', class_id=2, course='体比', teacher='李老师', periods=1),
    ]
    dataset = Dataset(grade='初三', classes=[1, 2],
                      teachers={n: Teacher(name=n) for n in ('王老师', '李老师')}, tasks=tasks)
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=t.id, class_id=t.class_id, course='体比',
                  teacher=t.teacher, slot=0) for t in tasks])
    rule = Rule(type='venue_capacity', scope={},
                params={'venue': '操场', 'capacity': 1})
    assert '场地超容' in kinds(verify(solution, dataset, cfg, [rule]))


# ---------------------------------------------------------------- I1：weekdays 限定

def test_daily_max_only_judges_the_listed_weekdays():
    """daily_max 带 weekdays 时，未列出的日子不该被判违规。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    from scheduler.core.rules import Rule
    cfg = load_config(CONFIG_DIR)
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=5)
    dataset = Dataset(grade='初三', classes=[1],
                      teachers={'李琼': Teacher(name='李琼')}, tasks=[task])
    # 5 节全在周二；规则只禁周一
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=0, class_id=1, course='语文', teacher='李琼',
                  slot=cal.slot_index(1, p)) for p in range(1, 6)])
    rule = Rule(type='daily_max', scope={'course': '语文'},
                params={'n': 0, 'weekdays': ['周一']})
    assert verify(solution, dataset, cfg, [rule]) == []
    # 同一份安排换成禁周二就必须报
    rule2 = Rule(type='daily_max', scope={'course': '语文'},
                 params={'n': 0, 'weekdays': ['周二']})
    assert '每日上限超出' in kinds(verify(solution, dataset, cfg, [rule2]))


def test_daily_min_only_judges_the_listed_weekdays():
    """daily_min 带 weekdays 时，未列出的日子没课也不算下限不足。"""
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    from scheduler.core.rules import Rule
    cfg = load_config(CONFIG_DIR)
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                        teacher='李琼', periods=1)
    dataset = Dataset(grade='初三', classes=[1],
                      teachers={'李琼': Teacher(name='李琼')}, tasks=[task])
    solution = Solution(status='FEASIBLE', wall_time=0.0, placements=[
        Placement(task_id=0, class_id=1, course='语文', teacher='李琼',
                  slot=cal.slot_index(0, 1))])
    ok = Rule(type='daily_min', scope={'course': '语文'},
              params={'n': 1, 'weekdays': ['周一']})
    assert verify(solution, dataset, cfg, [ok]) == []
    bad = Rule(type='daily_min', scope={'course': '语文'},
               params={'n': 1, 'weekdays': ['周一', '周二']})
    assert '每日下限不足' in kinds(verify(solution, dataset, cfg, [bad]))


# ---------------------------------------------------------------- I4：未知类型出声

def test_unsupported_hard_rule_type_is_reported(real):
    """硬规则没有校验实现时必须出声，否则「0 违规」是空话。"""
    from scheduler.core.rules import Rule
    cfg, dataset, rules, solution = real
    unknown = Rule(type='teacher_balance', scope={'grade': '初三'},
                   params={'max_daily': 6}, mode='hard')
    violations = verify(solution, dataset, cfg, [unknown])
    assert '规则未被校验' in kinds(violations)
    assert any('teacher_balance' in v.detail for v in violations)


def test_unsupported_soft_rule_type_stays_quiet(real):
    """软约束是 M4 的事，跳过不出声。"""
    from scheduler.core.rules import Rule
    cfg, dataset, rules, solution = real
    soft = Rule(type='teacher_balance', scope={'grade': '初三'},
                params={'max_daily': 6}, mode='soft', weight=5)
    assert verify(solution, dataset, cfg, [soft]) == []


# ---------------------------------------------------------------- I6：四条反例

def test_detects_teacher_double_booking(real):
    """把某位教师两个班的课挪到同一格 —— 必须报教师分身。"""
    cfg, dataset, rules, solution = real
    by_teacher = defaultdict(list)
    for p in solution.placements:
        if p.parity is None and not cfg.courses[p.course].multi_class:
            by_teacher[p.teacher].append(p)
    victim = other = None
    for group in by_teacher.values():
        anchor = group[0]
        pair = [p for p in group if p.class_id != anchor.class_id and p.slot != anchor.slot]
        if pair:
            victim, other = pair[0], anchor
            break
    assert victim is not None, '真实解里应能找到一位带两个班的教师'
    broken = tamper(solution, victim.task_id, victim.slot, other.slot)
    assert '教师分身' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_daily_max_overflow(real):
    """化学每天至多 1 节：把某节化学挪到同班已有化学的那天。"""
    cfg, dataset, rules, solution = real
    chem = [p for p in solution.placements
            if p.class_id == 1 and cfg.family_of(p.course) == '化学']
    assert len(chem) >= 2
    keep, victim = chem[0], chem[1]
    target_day = cal.slot_of(keep.slot)[0]
    taken = {q.slot for q in chem}
    free = next(cal.slot_index(target_day, p) for p in range(1, cal.PERIODS_PER_DAY + 1)
                if cal.slot_index(target_day, p) not in taken)
    broken = tamper(solution, victim.task_id, victim.slot, free)
    assert '每日上限超出' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_weekday_exact_mismatch(real):
    """体育周一三四各恰好 1 节：把周一那节挪去周三，两天都不符。"""
    cfg, dataset, rules, solution = real
    victim = next(p for p in solution.placements
                  if p.class_id == 1 and cfg.family_of(p.course) == '体育'
                  and cal.slot_of(p.slot)[0] == 0)
    target = next(s for s in range(cal.N_SLOTS)
                  if cal.slot_of(s)[0] == 2 and s != victim.slot)
    broken = tamper(solution, victim.task_id, victim.slot, target)
    assert '指定星期节数不符' in kinds(verify(broken, dataset, cfg, rules))


def test_detects_missing_consecutive(real):
    """语文要求 1 天连堂：把 1 班所有语文摊到互不相邻的格上。"""
    cfg, dataset, rules, solution = real
    placements = [p.model_copy() for p in solution.placements]
    spread = [cal.slot_index(d, p) for d in range(len(cal.DAYS)) for p in (1, 3)]
    moved = 0
    for p in placements:
        if p.class_id == 1 and p.course == '语文':
            p.slot = spread[moved]
            moved += 1
    assert moved >= 2
    broken = Solution(status='FEASIBLE', wall_time=0.0, placements=placements)
    assert '缺少连堂' in kinds(verify(broken, dataset, cfg, rules))
