import pytest
from scheduler.core.models import GradeCalendar
from scheduler.core.ruletext import parse_time_expr, RuleTextError

CAL = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                    periods_per_day=9, midday_break_after=5)


def S(day, *periods):
    """便捷构造：S(0, 4, 5) -> {(0,4),(0,5)}"""
    return {(day, p) for p in periods}


def test_empty_input_yields_empty_set():
    assert parse_time_expr('', CAL) == set()
    assert parse_time_expr(None, CAL) == set()
    assert parse_time_expr('   ', CAL) == set()


def test_bare_periods():
    # 班主任会：周一4、5节
    assert parse_time_expr('周一4、5节不排课', CAL) == S(0, 4, 5)


def test_whole_morning():
    assert parse_time_expr('周二上午不排课', CAL) == S(1, 1, 2, 3, 4, 5)


def test_whole_afternoon():
    assert parse_time_expr('周四下午不排课', CAL) == S(3, 6, 7, 8, 9)


def test_morning_with_numbers():
    assert parse_time_expr('周二上午2、3、4节不排课', CAL) == S(1, 2, 3, 4)
    assert parse_time_expr('周五上午1、2、3节不排课', CAL) == S(4, 1, 2, 3)


def test_afternoon_with_numbers_offsets_by_five():
    # 设计文档 5.3 节举的例子：周二下午2、3、4节 -> 第 7、8、9 节
    assert parse_time_expr('周二下午2、3、4节不排课', CAL) == S(1, 7, 8, 9)


def test_comma_between_digits_is_not_a_clause_separator():
    """「周五第4，5节」的逗号是数字分隔符 —— 按逗号切句会解析错。"""
    assert parse_time_expr('周五第4，5节不排课', CAL) == S(4, 4, 5)
    assert parse_time_expr('周二上午，周五第4，5节不排课', CAL) == S(1, 1, 2, 3, 4, 5) | S(4, 4, 5)


def test_multi_clause():
    assert parse_time_expr('周一4、5节，周三上午不排课', CAL) == S(0, 4, 5) | S(2, 1, 2, 3, 4, 5)
    assert parse_time_expr('周一4、5节，周四下午不排课', CAL) == S(0, 4, 5) | S(3, 6, 7, 8, 9)


def test_four_clause_with_di_prefix():
    text = '周一4、5节，周二上午，周四上午第2、3、4、5节，周五上午4、5节不排课'
    expected = S(0, 4, 5) | S(1, 1, 2, 3, 4, 5) | S(3, 2, 3, 4, 5) | S(4, 4, 5)
    assert parse_time_expr(text, CAL) == expected


def test_bare_numbers_are_absolute_periods():
    """无上午/下午标记时按绝对节次解释，结果须与带标记的同义写法一致。"""
    with_mark = '周一4、5节，周二上午，周四上午2、3、4、5节，周五上午4、5节不排课'
    without_mark = '周一4、5节，周四2、3、4、5节，周五4、5节不排课'
    assert parse_time_expr(without_mark, CAL) == S(0, 4, 5) | S(3, 2, 3, 4, 5) | S(4, 4, 5)
    assert parse_time_expr(with_mark, CAL) - S(1, 1, 2, 3, 4, 5) == parse_time_expr(without_mark, CAL)


# ---- Excel 中出现的全部 22 种非空写法，逐条核对 ----
CORPUS = [
    ('周二上午不排课', S(1, 1, 2, 3, 4, 5)),
    ('周一4、5节不排课', S(0, 4, 5)),
    ('周三上午不排课', S(2, 1, 2, 3, 4, 5)),
    ('周一4、5节，周三上午不排课', S(0, 4, 5) | S(2, 1, 2, 3, 4, 5)),
    ('周四下午不排课', S(3, 6, 7, 8, 9)),
    ('周二上午2、3、4节不排课', S(1, 2, 3, 4)),
    ('周一4、5节，周五上午不排课', S(0, 4, 5) | S(4, 1, 2, 3, 4, 5)),
    ('周五上午不排课', S(4, 1, 2, 3, 4, 5)),
    ('周五上午1、2、3节不排课', S(4, 1, 2, 3)),
    ('周一4、5节，周二上午不排课', S(0, 4, 5) | S(1, 1, 2, 3, 4, 5)),
    ('周一4、5节，周二上午，周四上午2、3、4、5节，周五上午4、5节不排课',
     S(0, 4, 5) | S(1, 1, 2, 3, 4, 5) | S(3, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周一4、5节，周四下午不排课', S(0, 4, 5) | S(3, 6, 7, 8, 9)),
    ('周一4、5节，周二上午，周五上午4、5节不排课',
     S(0, 4, 5) | S(1, 1, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周一4、5节，周二上午，周四上午第2、3、4、5节，周五上午4、5节不排课',
     S(0, 4, 5) | S(1, 1, 2, 3, 4, 5) | S(3, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周二上午，周五第4，5节不排课', S(1, 1, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周一4、5节，周四下午，周五上午4、5节不排课',
     S(0, 4, 5) | S(3, 6, 7, 8, 9) | S(4, 4, 5)),
    ('周四下午，周五第4，5节不排课', S(3, 6, 7, 8, 9) | S(4, 4, 5)),
    ('周三下午不排课', S(2, 6, 7, 8, 9)),
    ('周一4、5节，周四2、3、4、5节，周五4、5节不排课',
     S(0, 4, 5) | S(3, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周一4、5节，周三上午，周五上午第4、5节不排课',
     S(0, 4, 5) | S(2, 1, 2, 3, 4, 5) | S(4, 4, 5)),
    ('周一4、5节，周五上午1、2、3节不排课', S(0, 4, 5) | S(4, 1, 2, 3)),
    ('周三下午，周五第4，5节不排课', S(2, 6, 7, 8, 9) | S(4, 4, 5)),
]


def test_corpus_has_all_22_variants():
    assert len(CORPUS) == 22


@pytest.mark.parametrize('text,expected', CORPUS, ids=[c[0] for c in CORPUS])
def test_real_corpus(text, expected):
    assert parse_time_expr(text, CAL) == expected


def test_rejects_text_without_weekday():
    with pytest.raises(RuleTextError):
        parse_time_expr('每天都不排课', CAL)


def test_rejects_out_of_range_period():
    with pytest.raises(RuleTextError):
        parse_time_expr('周一下午9节不排课', CAL)
