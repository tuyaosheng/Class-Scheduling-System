import pytest
from scheduler.core import calendar as cal


def test_slot_space_is_45():
    assert cal.N_SLOTS == 45
    assert len(cal.DAYS) == 5
    assert cal.PERIODS_PER_DAY == 9


def test_slot_index_roundtrip():
    for day in range(5):
        for period in range(1, 10):
            idx = cal.slot_index(day, period)
            assert cal.slot_of(idx) == (day, period)


def test_slot_index_is_day_major():
    assert cal.slot_index(0, 1) == 0
    assert cal.slot_index(0, 9) == 8
    assert cal.slot_index(1, 1) == 9
    assert cal.slot_index(4, 9) == 44


def test_day_index():
    assert cal.day_index('周一') == 0
    assert cal.day_index('周五') == 4
    with pytest.raises(ValueError):
        cal.day_index('周六')


def test_section_period_morning_is_identity():
    assert cal.section_period('上午', 1) == 1
    assert cal.section_period('上午', 5) == 5


def test_section_period_afternoon_offsets_by_five():
    # 设计文档 5.3 节：下午第 N 节 = 第 5+N 节
    assert cal.section_period('下午', 1) == 6
    assert cal.section_period('下午', 2) == 7
    assert cal.section_period('下午', 4) == 9


def test_section_period_bare_number_is_absolute():
    assert cal.section_period(None, 4) == 4
    assert cal.section_period(None, 9) == 9


@pytest.mark.parametrize('section,n', [('上午', 6), ('下午', 5), ('下午', 0), (None, 10), (None, 0)])
def test_section_period_rejects_out_of_range(section, n):
    with pytest.raises(ValueError):
        cal.section_period(section, n)


def test_slot_index_rejects_bad_input():
    with pytest.raises(ValueError):
        cal.slot_index(5, 1)
    with pytest.raises(ValueError):
        cal.slot_index(0, 10)
