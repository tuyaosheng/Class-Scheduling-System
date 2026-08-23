from pathlib import Path

import pytest

from scheduler.core.config import load_config
from scheduler.core.models import TeachingTask
from scheduler.core.rules import (
    RELAXABLE, RULE_TYPES, Rule, RuleError, describe, load_rules, matches, select_tasks,
)

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'scheduler' / 'config'


@pytest.fixture(scope='module')
def cfg():
    return load_config(CONFIG_DIR)


def task(**kw):
    base = dict(id=0, grade='初三', class_id=1, course='物理', teacher='陈芬', periods=4)
    base.update(kw)
    return TeachingTask(**base)


def test_empty_scope_matches_everything(cfg):
    assert matches(Rule(type='daily_min'), task(), cfg)


def test_grade_scope(cfg):
    r = Rule(type='daily_min', scope={'grade': '初三'})
    assert matches(r, task(), cfg)
    assert not matches(r, task(grade='初二'), cfg)


def test_family_scope_catches_shadow_course(cfg):
    """family=物理 必须同时命中物理与综实1 —— 这是学科系概念的全部意义。"""
    r = Rule(type='daily_min', scope={'family': '物理'})
    assert matches(r, task(course='物理'), cfg)
    assert matches(r, task(course='综实1'), cfg)
    assert not matches(r, task(course='化学'), cfg)


def test_course_scope_does_not_catch_shadow_course(cfg):
    r = Rule(type='consecutive', scope={'course': '语文'})
    assert matches(r, task(course='语文'), cfg)
    assert not matches(r, task(course='综实2'), cfg)


def test_list_value_is_or(cfg):
    r = Rule(type='daily_min', scope={'family': ['语文', '数学', '英语', '物理']})
    assert matches(r, task(course='综实2'), cfg)     # 综实2 属数学系
    assert not matches(r, task(course='历史'), cfg)


def test_star_is_wildcard(cfg):
    assert matches(Rule(type='daily_min', scope={'grade': '*'}), task(grade='初一'), cfg)


def test_dims_are_anded(cfg):
    r = Rule(type='forbid_slots', scope={'grade': '初三', 'teacher': '陈芬'})
    assert matches(r, task(), cfg)
    assert not matches(r, task(teacher='李琼'), cfg)


def test_class_scope(cfg):
    r = Rule(type='daily_max', scope={'class': [1, 2, 3]})
    assert matches(r, task(class_id=2), cfg)
    assert not matches(r, task(class_id=9), cfg)


def test_unknown_scope_dim_rejected(cfg):
    with pytest.raises(RuleError, match='教室'):
        matches(Rule(type='daily_min', scope={'教室': 'A101'}), task(), cfg)


def test_unknown_rule_type_rejected():
    with pytest.raises(RuleError, match='fly_to_moon'):
        Rule(type='fly_to_moon').validate_type()


def test_all_13_types_declared():
    assert RULE_TYPES == frozenset({
        'forbid_slots', 'pin_window', 'daily_min', 'daily_max', 'weekday_exact',
        'consecutive', 'spacing', 'alternate_weeks', 'venue_capacity',
        'preferred_periods', 'avoid_after', 'teacher_balance', 'teacher_max_run',
    })


def test_relaxable_excludes_physical_constraints():
    assert 'daily_min' in RELAXABLE
    assert 'forbid_slots' not in RELAXABLE
    assert 'pin_window' not in RELAXABLE
    assert 'alternate_weeks' not in RELAXABLE


def test_select_tasks(cfg):
    tasks = [task(id=0, course='物理'), task(id=1, course='综实1'), task(id=2, course='化学')]
    picked = select_tasks(Rule(type='daily_min', scope={'family': '物理'}), tasks, cfg)
    assert [t.id for t in picked] == [0, 1]


def test_load_generated_rules(cfg):
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    assert any(r.type == 'daily_min' for r in rules)
    assert all(r.type in RULE_TYPES for r in rules)


def test_generated_rules_include_reserved_slot_forbid(cfg):
    """校本1/综实2/体比/体选/班会已改为教务固定安排（external），不再生成 pin_window；
    取而代之的是一条年级级的 forbid_slots，把这 8 格整体挖空。"""
    rules = load_rules(CONFIG_DIR / 'rules.yaml', CONFIG_DIR / 'rules.generated.yaml')
    assert not any(r.type == 'pin_window' for r in rules)
    reserved = [r for r in rules if r.type == 'forbid_slots' and 'teacher' not in r.scope]
    assert len(reserved) == 1
    assert len(reserved[0].params['slots']) == 8


def test_describe_is_human_readable(cfg):
    r = Rule(type='daily_min', scope={'grade': '初三', 'family': '物理'}, params={'n': 1})
    text = describe(r)
    assert '物理' in text and '每天至少' in text
