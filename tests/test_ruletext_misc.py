import pytest
from scheduler.core.ruletext import (
    parse_fixed_slots, parse_requirement, parse_remark, RuleTextError,
)


def test_fixed_slots_single():
    # 班会：周一第9节，1 格放 1 节，退化为钉死
    assert parse_fixed_slots('周一第9节') == {(0, 9)}


def test_fixed_slots_window():
    # 体比周课时 1，窗口 2 格 —— 语义是「在这 2 格里占 1 格」
    assert parse_fixed_slots('周二第8、9节') == {(1, 8), (1, 9)}
    assert parse_fixed_slots('周三第8、9节') == {(2, 8), (2, 9)}
    assert parse_fixed_slots('周四第8、9节') == {(3, 8), (3, 9)}
    assert parse_fixed_slots('周五第9节') == {(4, 9)}


def test_fixed_slots_empty():
    assert parse_fixed_slots('') == set()
    assert parse_fixed_slots(None) == set()


def test_requirement_daily_min():
    assert parse_requirement('保证每天有1节') == [
        {'type': 'daily_min', 'params': {'n': 1}}
    ]


def test_requirement_daily_max_is_n_minus_one():
    """「当天不能排2节」意为最多 1 节 —— 写成 n=2 是错的。"""
    assert parse_requirement('同一个班当天不能排2节') == [
        {'type': 'daily_max', 'params': {'n': 1}}
    ]


def test_requirement_weekday_exact():
    assert parse_requirement('保证周一三四每天1节') == [
        {'type': 'weekday_exact',
         'params': {'weekdays': ['周一', '周三', '周四'], 'n': 1}}
    ]


def test_requirement_alternate_art_side():
    # 这一行是美术老师填的（她说「与心理课分单双周」），美术上单周
    assert parse_requirement('与心理课分单双周上，即"心美"周课时1节') == [
        {'type': 'alternate_weeks',
         'params': {'pair': ['美术', '心理'], 'self_parity': '单周'}}
    ]


def test_requirement_alternate_psych_side():
    assert parse_requirement('与美术课分单双周上，即"心美"周课时1节') == [
        {'type': 'alternate_weeks',
         'params': {'pair': ['美术', '心理'], 'self_parity': '双周'}}
    ]


def test_requirement_alternate_tolerates_curly_quotes():
    """Excel 里用的是全角引号，正则不能依赖引号字符。"""
    assert parse_requirement('与心理课分单双周上，即“心美”周课时1节')[0]['type'] == 'alternate_weeks'


def test_requirement_empty():
    assert parse_requirement('') == []
    assert parse_requirement(None) == []


def test_remark_yields_consecutive_and_spacing():
    text = '其中一天为连堂课，两个班之间要隔开1节，或分开上下午各2节'
    assert parse_remark(text) == [
        {'type': 'consecutive', 'params': {'days': 1, 'length': 2}},
        {'type': 'spacing', 'params': {'min_gap': 1}},
    ]


def test_remark_empty():
    assert parse_remark('') == []
    assert parse_remark(None) == []


def test_unknown_requirement_raises():
    with pytest.raises(RuleTextError):
        parse_requirement('每周必须在操场上两节')


def test_unknown_remark_raises():
    with pytest.raises(RuleTextError):
        parse_remark('这个班比较活跃')

