"""L3 AI 审核：课表出表后自动体检。

【铁律5】AI 不做算术、不做硬性判定——撞课、课时数、容量是否够全部由
确定性代码（precheck.py 的 L1、verifier.py 的独立校验）回答，本模块只
把那些结论、以及下面几项确定性统计，当作既定事实喂给 prompt。AI 只做
两件事：发现规则没覆盖但一眼能看出不合理的编排；指出规则配置本身的疏漏。
真实案例（设计文档 §9）：7 班周一排了 2 节数学，规则只写了「每天至少 1 节」
（下限）没写上限，因此完全合法——但教务一眼即知不合理，这正是本模块的目标场景。
"""
import json
from collections import defaultdict
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from scheduler.core.rules import describe

_SYSTEM_PROMPT = (
    "你是中小学排课系统的课表审核员。你会收到一份已经排定的课表、生效的排课"
    "规则列表、独立校验器给出的确定性结论、以及若干统计指标。这些结论和数字"
    "都是已经算好的既定事实，你不需要也不能重新核算是否撞课、课时数是否够、"
    "场地容量是否超——你的任务只有两件事：1) 发现规则没有覆盖、但一眼就能看"
    "出不合理的编排；2) 指出规则配置本身的疏漏。只返回 JSON 数组本体，不要"
    "任何解释文字、不要代码块标记，没有发现问题就返回 []。"
)

_USER_TEMPLATE = (
    "课表（紧凑文本，每行一个班级）：\n{schedule_text}\n\n"
    "生效规则：\n{rules_text}\n\n"
    "独立校验器结论（{n_violations} 处确定性违规，已是既定事实）：\n{violations_text}\n\n"
    "统计指标（已算好，不要重新核算）：\n{stats_text}\n\n"
    "返回 JSON 数组，每项字段：\n"
    'severity: "info" 或 "warning"\n'
    'scope: {{"class": 班号, "day": "周几"}} 之类，按问题实际涉及范围填，字段可缺省\n'
    'issue: 用教务能听懂的中文描述问题\n'
    'suggestion: 具体的规则调整建议\n'
)


class Finding(BaseModel):
    severity: str
    scope: Dict = Field(default_factory=dict)
    issue: str
    suggestion: str = ''


class AIReviewError(RuntimeError):
    """AI 审核失败：网络错误、超时，或返回内容不满足 schema。"""


def _default_client():
    import anthropic
    from scheduler.core.settings_store import get_ai_api_key
    api_key = get_ai_api_key()
    if not api_key:
        raise AIReviewError("未配置 Anthropic API key：请在系统「设置 → AI 设置」里填写，"
                            "或设置环境变量 ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key)


def _schedule_text(solution, dataset) -> str:
    calendar = dataset.calendar
    by_class: Dict[int, Dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for p in solution.placements:
        day, period = calendar.slot_of(p.slot)
        by_class[p.class_id][day].append((period, p.course))

    lines = []
    for class_id in sorted(by_class):
        day_parts = []
        for day in range(len(calendar.days)):
            periods = sorted(by_class[class_id].get(day, []))
            if not periods:
                continue
            text = '、'.join('第%d节%s' % (period, course) for period, course in periods)
            day_parts.append('%s%s' % (calendar.days[day], text))
        lines.append('%d班 —— %s' % (class_id, '；'.join(day_parts)))
    return '\n'.join(lines) if lines else '（空课表）'


def _rules_text(rules) -> str:
    active = [r for r in rules if r.enabled]
    if not active:
        return '（无生效规则）'
    return '\n'.join(describe(r) for r in active)


def _violations_text(violations) -> str:
    if not violations:
        return '（校验器未发现任何违规）'
    return '\n'.join('- [%s] %s' % (v.kind, v.detail) for v in violations)


def _daily_family_hotspots(solution, dataset, cfg) -> List[str]:
    """同一个班同一天同一个学科系排了 >=2 节——多数规则只写下限没写上限，
    这类编排完全合法但常常不合理，是本模块最典型的目标场景。"""
    calendar = dataset.calendar
    counts: Dict[tuple, int] = defaultdict(int)
    for p in solution.placements:
        day, _ = calendar.slot_of(p.slot)
        family = cfg.family_of(dataset.grade, p.course)
        counts[(p.class_id, family, day)] += 1
    return [
        '%d班%s%s：%d节' % (class_id, calendar.days[day], family, n)
        for (class_id, family, day), n in sorted(counts.items())
        if n >= 2
    ]


def _teacher_load_spread(solution, dataset) -> List[str]:
    """教师每天课时数的跨度——跨度大说明某几天特别集中、某几天几乎没课。"""
    calendar = dataset.calendar
    per_teacher_day: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for p in solution.placements:
        day, _ = calendar.slot_of(p.slot)
        per_teacher_day[p.teacher][day] += 1

    lines = []
    for teacher, day_counts in sorted(per_teacher_day.items()):
        counts = [day_counts.get(d, 0) for d in range(len(calendar.days))]
        spread = max(counts) - min(counts)
        if spread >= 3:
            lines.append('%s：%s（跨度 %d）' % (teacher, '/'.join(map(str, counts)), spread))
    return lines


def _consecutive_family_runs(solution, dataset, cfg) -> List[str]:
    """相邻两节课同一个学科系（连堂）——不跨午休边界。"""
    calendar = dataset.calendar
    by_class_day: Dict[tuple, Dict[int, str]] = defaultdict(dict)
    for p in solution.placements:
        day, period = calendar.slot_of(p.slot)
        by_class_day[(p.class_id, day)][period] = cfg.family_of(dataset.grade, p.course)

    lines = []
    for (class_id, day), period_family in sorted(by_class_day.items()):
        for period in sorted(period_family):
            if period == calendar.midday_break_after:
                continue
            nxt = period + 1
            if nxt in period_family and period_family[nxt] == period_family[period]:
                lines.append('%d班%s第%d-%d节连堂%s' % (
                    class_id, calendar.days[day], period, nxt, period_family[period]))
    return lines


def _stats_text(solution, dataset, cfg) -> str:
    def _section(title, lines):
        return '%s：\n%s' % (title, '\n'.join(lines) if lines else '（无）')

    return '\n\n'.join([
        _section('同一天同学科系排了 2 节及以上', _daily_family_hotspots(solution, dataset, cfg)),
        _section('日课时跨度 >= 3 的教师', _teacher_load_spread(solution, dataset)),
        _section('连堂（相邻两节同学科系）', _consecutive_family_runs(solution, dataset, cfg)),
    ])


def review_schedule(solution, dataset, cfg, rules, violations, *, client=None) -> List[Finding]:
    try:
        client = client or _default_client()
        prompt = _USER_TEMPLATE.format(
            schedule_text=_schedule_text(solution, dataset),
            rules_text=_rules_text(rules),
            n_violations=len(violations),
            violations_text=_violations_text(violations),
            stats_text=_stats_text(solution, dataset, cfg),
        )
        response = client.messages.create(
            model='claude-sonnet-4-5', max_tokens=2048,
            system=_SYSTEM_PROMPT, messages=[{'role': 'user', 'content': prompt}],
        )
        raw_text = response.content[0].text
    except AIReviewError:
        raise
    except Exception as exc:
        raise AIReviewError('AI 审核失败：%s，可稍后重试' % exc) from exc

    try:
        data = json.loads(raw_text)
        findings = [Finding(**item) for item in data]
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AIReviewError('AI 审核失败：返回内容不满足格式') from exc
    return findings
