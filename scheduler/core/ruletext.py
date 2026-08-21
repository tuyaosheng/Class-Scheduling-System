"""中文规则文本解析。

Excel 后四列是教务手写的自然语言。这里把它们转成结构化数据。
解析结果必须回显给用户确认（见 cli.py 的 import 子命令），不能让歧义静默通过。
"""
import re

from . import calendar as cal


class RuleTextError(ValueError):
    """规则文本无法解析。"""


_WEEKDAY_RE = re.compile(r'周[一二三四五]')
_DIGITS_RE = re.compile(r'\d+')


def _split_clauses(text):
    """按「周X」锚点切句。不按逗号切 —— 逗号可能是数字分隔符。"""
    anchors = list(_WEEKDAY_RE.finditer(text))
    if not anchors:
        raise RuleTextError('文本中找不到星期：%r' % text)
    clauses = []
    for i, m in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(text)
        clauses.append((m.group(), text[m.end():end]))
    return clauses


def parse_time_expr(text):
    """解析禁排/固定节次文本，返回 {(day_index, period)} 集合。"""
    if not text or not str(text).strip():
        return set()
    text = str(text).strip()
    slots = set()
    for weekday, body in _split_clauses(text):
        day = cal.day_index(weekday)
        section = '上午' if '上午' in body else ('下午' if '下午' in body else None)
        numbers = [int(n) for n in _DIGITS_RE.findall(body)]
        if numbers:
            for n in numbers:
                try:
                    slots.add((day, cal.section_period(section, n)))
                except ValueError as exc:
                    raise RuleTextError('%s%r: %s' % (weekday, body, exc)) from exc
        elif section == '上午':
            slots.update((day, p) for p in cal.MORNING)
        elif section == '下午':
            slots.update((day, p) for p in cal.AFTERNOON)
        else:
            slots.update((day, p) for p in range(1, cal.PERIODS_PER_DAY + 1))
    return slots
