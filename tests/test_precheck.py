from pathlib import Path

import pytest

from scheduler.core import calendar as cal
from scheduler.core.config import load_config
from scheduler.core.importer import import_excel
from scheduler.core.models import Dataset, Teacher, TeachingTask
from scheduler.core.precheck import format_issues, precheck
from scheduler.core.rules import Rule, load_rules

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / 'scheduler' / 'config'
EXCEL = ROOT / '任课与排课说明.xlsx'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def test_real_data_passes_precheck(cfg):
    """真实初三数据可排（设计文档实测 OPTIMAL），预检不该报任何问题。"""
    result = import_excel(EXCEL, cfg, grade='初三')
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    issues = precheck(result.dataset, cfg, rules)
    assert issues == [], format_issues(issues)


def ds(tasks, teachers=None):
    return Dataset(grade='初三', classes=sorted({t.class_id for t in tasks}),
                   teachers=teachers or {t.teacher: Teacher(name=t.teacher) for t in tasks},
                   tasks=tasks)


def kinds(issues):
    return {i.kind for i in issues}


def test_teacher_overload_reports_exact_gap(cfg):
    """设计文档 §8 的示例格式：需要 48 节，可用 42 格，缺 6 格。

    用不带 reserved_slots 的裸 cfg，避免这个纯算术场景被教务固定占位的 8 格干扰。
    """
    bare_cfg = cfg.model_copy(update={'reserved_slots': {}})
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='语文',
                          teacher='梁艳红', periods=6) for i in range(8)]     # 48 节
    teachers = {'梁艳红': Teacher(name='梁艳红',
                                  forbidden=[[0, 4], [0, 5], [4, 1]])}        # 占 3 格
    issues = precheck(ds(tasks, teachers), bare_cfg, [])
    assert '教师超载' in kinds(issues)
    detail = next(i.detail for i in issues if i.kind == '教师超载')
    assert '梁艳红' in detail and '48' in detail and '42' in detail and '6' in detail


def test_class_capacity_accounts_for_reserved_slots(cfg):
    """37 节课占满系统可用格位（45-8），38 节就该报超载，而不是拿 45 当上限。"""
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='语文',
                          teacher='A', periods=38)]
    issues = precheck(ds(tasks), cfg, [])
    assert '班级超载' in kinds(issues)
    detail = next(i.detail for i in issues if i.kind == '班级超载')
    assert '37' in detail and '教务固定占位 8 格' in detail


def test_class_overload(cfg):
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='A', periods=30),
        TeachingTask(id=1, grade='初三', class_id=1, course='数学', teacher='B', periods=20),
    ]
    issues = precheck(ds(tasks), cfg, [])
    assert '班级超载' in kinds(issues)
    assert '50' in next(i.detail for i in issues if i.kind == '班级超载')


def test_daily_min_contradiction_named_by_family(cfg):
    """物理 4 节配「每天 1 节」，缺了综实1 就自相矛盾。"""
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='物理',
                          teacher='陈芬', periods=4)]
    rule = Rule(type='daily_min', scope={'family': '物理'}, params={'n': 1})
    issues = precheck(ds(tasks), cfg, [rule])
    assert '规则自相矛盾' in kinds(issues)
    detail = next(i.detail for i in issues if i.kind == '规则自相矛盾')
    assert '物理' in detail and '4' in detail and '5' in detail


def test_daily_min_satisfied_by_whole_family(cfg):
    """加上综实1 后矛盾消解 —— 学科系口径的直接验证。"""
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=1, course='物理', teacher='陈芬', periods=4),
        TeachingTask(id=1, grade='初三', class_id=1, course='综实1', teacher='陈芬', periods=1),
    ]
    rule = Rule(type='daily_min', scope={'family': '物理'}, params={'n': 1})
    assert '规则自相矛盾' not in kinds(precheck(ds(tasks), cfg, [rule]))


def test_daily_max_contradiction(cfg):
    """6 节课每天最多 1 节，5 天装不下。"""
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='化学',
                          teacher='王林', periods=6)]
    rule = Rule(type='daily_max', scope={'family': '化学'}, params={'n': 1})
    assert '规则自相矛盾' in kinds(precheck(ds(tasks), cfg, [rule]))


def test_pin_window_too_small(cfg):
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='体比',
                          teacher='周志宁', periods=3)]
    rule = Rule(type='pin_window', scope={'course': '体比'},
                params={'slots': [[1, 8], [1, 9]]})
    issues = precheck(ds(tasks), cfg, [rule])
    assert '固定窗口容量不足' in kinds(issues)


def test_pin_window_exactly_fits_is_ok(cfg):
    tasks = [TeachingTask(id=0, grade='初三', class_id=1, course='班会',
                          teacher='李琼', periods=1)]
    rule = Rule(type='pin_window', scope={'course': '班会'}, params={'slots': [[0, 9]]})
    assert precheck(ds(tasks), cfg, [rule]) == []


def test_venue_capacity_shortfall(cfg):
    """物理实验室 3 间 × 45 格 = 135 容量，需求 200 节放不下。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='综实1',
                          teacher='T%d' % i, periods=40) for i in range(5)]
    issues = precheck(ds(tasks), cfg, [])
    assert '场地容量不足' in kinds(issues)
    assert '物理实验室' in next(i.detail for i in issues if i.kind == '场地容量不足')


def test_null_capacity_venue_is_never_short(cfg):
    """操场 capacity 为 null = 不限制。"""
    tasks = [TeachingTask(id=i, grade='初三', class_id=i + 1, course='体育',
                          teacher='T%d' % i, periods=40) for i in range(20)]
    assert '场地容量不足' not in kinds(precheck(ds(tasks), cfg, []))


def test_precheck_is_fast(cfg):
    """毫秒级 —— 这是 L1 存在的理由。"""
    import time
    result = import_excel(EXCEL, cfg, grade='初三')
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    started = time.time()
    precheck(result.dataset, cfg, rules)
    assert time.time() - started < 0.5


def test_format_issues_readable():
    from scheduler.core.precheck import Issue
    text = format_issues([Issue(kind='教师超载', detail='梁艳红需要 48 节，可用 42 格，缺 6 格')])
    assert '[教师超载]' in text and '缺 6 格' in text
