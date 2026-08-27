"""calendar_import.py 的解析结果必须跟 calendars.yaml 里已经手写好的
七/八/九年级数据吻合——那份数据就是从同一份『作息表模板.xlsx』人工抄出来的，
用它当校验基准，不用另外编造预期值。
"""
from pathlib import Path

import pytest

from scheduler.core.calendar_import import (
    CalendarParseError, _infer_midday_break, _parse_time_range, parse_calendar_workbook,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / '作息表模板.xlsx'


def test_parse_time_range_handles_fullwidth_and_halfwidth_dash():
    assert _parse_time_range('8:25－9:05') == ('8:25', '9:05')
    assert _parse_time_range('10:15-10:55') == ('10:15', '10:55')


def test_parse_time_range_rejects_garbage():
    with pytest.raises(CalendarParseError):
        _parse_time_range('第一节课')


def test_infer_midday_break_finds_the_largest_gap():
    # 七年级真实数据：第4、5节之间有 2 小时多的午休缺口，其余都是 15-55 分钟。
    clock_times = [('8:25', '9:05'), ('9:20', '10:00'), ('10:15', '10:55'),
                   ('11:10', '11:50'), ('14:20', '15:00'), ('15:15', '15:55'),
                   ('16:10', '16:50'), ('16:50', '17:30')]
    assert _infer_midday_break(clock_times) == 4


@pytest.mark.skipif(not TEMPLATE.exists(), reason='作息表模板.xlsx 不在仓库里')
def test_parses_real_template_matching_calendars_yaml():
    sheets = {s.sheet_name: s for s in parse_calendar_workbook(TEMPLATE)}
    assert set(sheets) == {'七年级', '八年级', '九年级'}

    grade7 = sheets['七年级']
    assert grade7.periods_per_day == 8
    assert grade7.midday_break_after == 4
    assert grade7.clock_times[0] == ('8:25', '9:05')
    assert grade7.clock_times[-1] == ('16:50', '17:30')

    grade9 = sheets['九年级']
    assert grade9.periods_per_day == 9
    assert grade9.midday_break_after == 5
    assert grade9.clock_times[0] == ('8:00', '8:40')

    grade8 = sheets['八年级']
    assert grade8.periods_per_day == 9
    assert grade8.midday_break_after == 5
