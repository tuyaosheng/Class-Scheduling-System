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


WEEKDAY_CHARS = '一二三四五'

_REQ_DAILY_MIN_RE = re.compile(r'保证每天有(\d+)节')
_REQ_DAILY_MAX_RE = re.compile(r'同一个班当天不能排(\d+)节')
_REQ_WEEKDAY_RE = re.compile(r'保证周([一二三四五]+)每天(\d+)节')
_REQ_ALT_RE = re.compile(r'与(心理|美术)课分单双周上')
_REMARK_SPACING_RE = re.compile(r'两个班之间要隔开(\d+)节')

# 文本里提到的是「对方」，所以本行课程的周次是对方的反面。
# 美术上单周、心理上双周（设计文档 3.3 节）。
_ALT_SELF_PARITY = {'心理': '单周', '美术': '双周'}


def parse_fixed_slots(text):
    """解析「固定节次」列。语义是窗口：在这些格里排完该课的周课时。"""
    return parse_time_expr(text)


def parse_requirement(text):
    """解析「排课要求」列，返回规则片段列表。"""
    if not text or not str(text).strip():
        return []
    text = str(text).strip()

    m = _REQ_WEEKDAY_RE.search(text)
    if m:
        days = ['周' + ch for ch in m.group(1)]
        return [{'type': 'weekday_exact',
                 'params': {'weekdays': days, 'n': int(m.group(2))}}]

    m = _REQ_DAILY_MAX_RE.search(text)
    if m:
        # 「不能排 N 节」= 最多 N-1 节
        return [{'type': 'daily_max', 'params': {'n': int(m.group(1)) - 1}}]

    m = _REQ_DAILY_MIN_RE.search(text)
    if m:
        return [{'type': 'daily_min', 'params': {'n': int(m.group(1))}}]

    m = _REQ_ALT_RE.search(text)
    if m:
        return [{'type': 'alternate_weeks',
                 'params': {'pair': ['美术', '心理'],
                            'self_parity': _ALT_SELF_PARITY[m.group(1)]}}]

    raise RuleTextError('无法识别的排课要求：%r' % text)


def parse_remark(text):
    """解析「备注」列。"""
    if not text or not str(text).strip():
        return []
    text = str(text).strip()
    out = []
    if '连堂' in text:
        out.append({'type': 'consecutive', 'params': {'days': 1, 'length': 2}})
    m = _REMARK_SPACING_RE.search(text)
    if m:
        out.append({'type': 'spacing', 'params': {'min_gap': int(m.group(1))}})
    if not out:
        raise RuleTextError('无法识别的备注：%r' % text)
    return out
