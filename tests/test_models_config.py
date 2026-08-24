from pathlib import Path

import pytest

from scheduler.core.config import load_config, ConfigError, SchedulerConfig
from scheduler.core.models import Course, Venue, TeachingTask

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def test_loads_17_courses(cfg):
    assert len(cfg.courses) == 17


def test_shadow_courses_map_to_主科_family(cfg):
    """影子课必须并入主科学科系 —— 按课程名统计会直接导致无解。"""
    assert cfg.family_of('综实1') == '物理'
    assert cfg.family_of('校本1') == '英语'
    assert cfg.family_of('综实2') == '数学'
    assert cfg.family_of('体比') == '体育'
    assert cfg.family_of('体选') == '体育'


def test_physics_family_has_five_periods(cfg):
    """物理 4 节 + 综实1 1 节 = 5 节，「每天 1 节」才成立。"""
    plan = cfg.plans['初三']
    total = sum(plan[c] for c in cfg.courses_in_family('物理') if c in plan)
    assert total == 5


def test_alternate_pair(cfg):
    assert cfg.courses['美术'].alternate == '单周'
    assert cfg.courses['心理'].alternate == '双周'
    assert cfg.courses['美术'].family == cfg.courses['心理'].family == '心美'


def test_venues(cfg):
    assert cfg.venues['物理实验室'].capacity == 3
    assert cfg.venues['操场'].capacity is None    # 不限制
    assert cfg.courses['综实1'].venue == '物理实验室'
    assert cfg.courses['音乐'].venue is None      # 音乐在普通教室上


def test_resolve_plan_key_expands_alternate_family(cfg):
    assert cfg.resolve_plan_key('心美') == ['美术', '心理']
    assert cfg.resolve_plan_key('语文') == ['语文']


def test_grade3_plan_totals_37_slots(cfg):
    """每班 37 节课占用系统求解的 37 格（另 8 格教务固定安排，见 reserved_slots）。"""
    assert sum(cfg.plans['初三'].values()) == 37
    cfg.validate_plan('初三')


def test_grade3_reserved_slots_are_eight(cfg):
    """周一T9/周二T8T9/周三T8T9/周四T8T9/周五T9 共 8 格，系统不建模不校验。"""
    assert len(cfg.reserved_slots['初三']) == 8
    assert len(cfg.reserved_slot_indices('初三')) == 8


def test_empty_plan_is_allowed(cfg):
    """初一初二计划待补，空计划不应报错。"""
    cfg.validate_plan('初一')


def test_validate_plan_rejects_overflow():
    bad = SchedulerConfig(
        courses={'语文': Course(name='语文', family='语文')},
        plans={'初三': {'语文': 50}},
        venues={},
    )
    with pytest.raises(ConfigError, match='超出'):
        bad.validate_plan('初三')


def test_validate_plan_rejects_unknown_course():
    bad = SchedulerConfig(
        courses={'语文': Course(name='语文', family='语文')},
        plans={'初三': {'围棋': 1}},
        venues={},
    )
    with pytest.raises(ConfigError, match='围棋'):
        bad.validate_plan('初三')


def test_config_rejects_course_with_unknown_venue(tmp_path):
    (tmp_path / 'courses.yaml').write_text(
        'courses:\n  - {name: 化学, family: 化学, venue: 天文台}\n', encoding='utf-8')
    (tmp_path / 'plans.yaml').write_text('plans: {初三: {化学: 1}}\n', encoding='utf-8')
    (tmp_path / 'venues.yaml').write_text('venues: []\n', encoding='utf-8')
    with pytest.raises(ConfigError, match='天文台'):
        load_config(tmp_path)


def test_teaching_task_model():
    t = TeachingTask(id=1, grade='初三', class_id=7, course='美术',
                     teacher='梁艳红', periods=1, parity='单周')
    assert t.parity == '单周'
    assert TeachingTask(id=2, grade='初三', class_id=7, course='语文',
                        teacher='李琼', periods=6).parity is None


def test_grade_calendar_slot_round_trip():
    from scheduler.core.models import GradeCalendar
    calendar = GradeCalendar(
        days=['周一', '周二', '周三', '周四', '周五'],
        periods_per_day=9,
        midday_break_after=5,
    )
    assert calendar.n_slots == 45
    assert calendar.slot_index(1, 8) == 16
    assert calendar.slot_of(16) == (1, 8)
    assert calendar.day_index('周三') == 2
    assert calendar.morning == range(1, 6)
    assert calendar.afternoon == range(6, 10)
    assert (5, 6) not in calendar.adjacent_pairs()
    assert (4, 5) in calendar.adjacent_pairs()


def test_grade_calendar_section_period():
    from scheduler.core.models import GradeCalendar
    calendar = GradeCalendar(days=['周一'], periods_per_day=9, midday_break_after=5)
    assert calendar.section_period('上午', 3) == 3
    assert calendar.section_period('下午', 2) == 7
    assert calendar.section_period(None, 9) == 9
    with pytest.raises(ValueError):
        calendar.section_period('上午', 6)


def test_dataset_calendar_defaults_to_current_global_shape():
    from scheduler.core.models import Dataset, Teacher, TeachingTask
    task = TeachingTask(id=0, grade='初三', class_id=1, course='语文', teacher='A', periods=1)
    ds = Dataset(grade='初三', classes=[1], teachers={'A': Teacher(name='A')}, tasks=[task])
    assert ds.calendar.n_slots == 45
    assert ds.calendar.periods_per_day == 9
    assert ds.calendar.midday_break_after == 5
