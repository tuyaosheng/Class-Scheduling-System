import json
from types import SimpleNamespace

import pytest

from scheduler.ai.reviewer import (
    AIReviewError, Finding, _consecutive_family_runs, _daily_family_hotspots,
    _teacher_load_spread, review_schedule,
)
from scheduler.core.config import SchedulerConfig
from scheduler.core.models import Course, Dataset, GradeCalendar, Teacher, TeachingTask
from scheduler.core.solver import Placement, Solution

CAL = GradeCalendar(days=['周一', '周二', '周三', '周四', '周五'],
                    periods_per_day=9, midday_break_after=5)


class FakeClient:
    """模拟 scheduler.ai.client 统一接口（complete），不是某个供应商 SDK 的
    形状——reviewer.py 现在只依赖这一层抽象。"""

    def __init__(self, text):
        self._text = text
        self.calls = []

    def complete(self, system, user, max_tokens=1024):
        self.calls.append((system, user, max_tokens))
        return self._text


def _dataset():
    tasks = [
        TeachingTask(id=0, grade='初三', class_id=7, course='数学', teacher='梁老师', periods=2),
        TeachingTask(id=1, grade='初三', class_id=7, course='语文', teacher='张老师', periods=1),
    ]
    teachers = {name: Teacher(name=name) for name in ('梁老师', '张老师')}
    return Dataset(grade='初三', classes=[7], teachers=teachers, tasks=tasks, calendar=CAL)


def _cfg():
    courses = {
        '数学': Course(name='数学', family='数学'),
        '语文': Course(name='语文', family='语文'),
    }
    return SchedulerConfig(courses={'初三': courses}, plans={}, venues={}, reserved_slots={})


def _solution_two_math_same_day():
    """7 班周一排了 2 节数学——设计文档 §9 的真实案例：规则只写了下限，
    这种编排完全合法但一眼就不合理。"""
    placements = [
        Placement(task_id=0, class_id=7, course='数学', teacher='梁老师', slot=0, parity=None),
        Placement(task_id=0, class_id=7, course='数学', teacher='梁老师', slot=2, parity=None),
        Placement(task_id=1, class_id=7, course='语文', teacher='张老师', slot=10, parity=None),
    ]
    return Solution(status='OPTIMAL', wall_time=0.1, placements=placements)


def test_daily_family_hotspots_flags_two_periods_same_family_same_day():
    hotspots = _daily_family_hotspots(_solution_two_math_same_day(), _dataset(), _cfg())
    assert hotspots == ['7班周一数学：2节']


def test_teacher_load_spread_flags_uneven_days():
    placements = [
        Placement(task_id=0, class_id=7, course='数学', teacher='梁老师', slot=s, parity=None)
        for s in (0, 1, 2, 3)   # 全部排在周一（第 1-4 节）
    ]
    solution = Solution(status='OPTIMAL', wall_time=0.1, placements=placements)
    spread = _teacher_load_spread(solution, _dataset())
    assert spread == ['梁老师：4/0/0/0/0（跨度 4）']


def test_consecutive_family_runs_detects_adjacent_same_family_but_not_across_midday_break():
    # slot 4 = 周一第5节，slot 5 = 周一第6节——跨过午休边界（midday_break_after=5），
    # 不该被算作连堂；slot 0/1（第1、2节）算连堂。
    placements = [
        Placement(task_id=0, class_id=7, course='数学', teacher='梁老师', slot=0, parity=None),
        Placement(task_id=0, class_id=7, course='数学', teacher='梁老师', slot=1, parity=None),
        Placement(task_id=1, class_id=7, course='语文', teacher='张老师', slot=4, parity=None),
        Placement(task_id=1, class_id=7, course='语文', teacher='张老师', slot=5, parity=None),
    ]
    solution = Solution(status='OPTIMAL', wall_time=0.1, placements=placements)
    runs = _consecutive_family_runs(solution, _dataset(), _cfg())
    assert runs == ['7班周一第1-2节连堂数学']


def test_review_schedule_parses_findings_from_valid_json():
    payload = [{
        'severity': 'warning',
        'scope': {'class': 7, 'day': '周一'},
        'issue': '7班周一有2节数学，规则只约束了下限未约束上限',
        'suggestion': '为数学系增加 daily_max: 1 规则',
    }]
    client = FakeClient(json.dumps(payload))
    findings = review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], [], client=client)
    assert findings == [Finding(**payload[0])]


def test_review_schedule_sends_deterministic_facts_not_left_for_ai_to_recompute():
    client = FakeClient('[]')
    violations = [SimpleNamespace(kind='教师分身', detail='梁老师撞课')]
    review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], violations, client=client)

    prompt = client.calls[0][1]
    assert '梁老师撞课' in prompt
    assert '7班' in prompt and '数学' in prompt


def test_raises_on_malformed_json():
    client = FakeClient('这不是 JSON')
    with pytest.raises(AIReviewError, match='审核失败'):
        review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], [], client=client)


def test_raises_when_client_call_fails():
    class BrokenClient:
        def complete(self, system, user, max_tokens=1024):
            raise ConnectionError('网络不通')

    with pytest.raises(AIReviewError, match='审核失败'):
        review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], [], client=BrokenClient())


def test_raises_on_missing_api_key_for_the_anthropic_provider(monkeypatch):
    """默认供应商是 OpenAI 兼容协议，这里显式选中 anthropic 来测它自己的缺 key 报错。"""
    import scheduler.core.settings_store as store
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(store, 'get_setting',
                        lambda key: 'anthropic' if key == 'ai.provider' else None)
    with pytest.raises(AIReviewError, match='API key'):
        review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], [])


def test_raises_on_incomplete_openai_compatible_config(monkeypatch):
    import scheduler.core.settings_store as store
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(store, 'get_setting', lambda key: None)
    with pytest.raises(AIReviewError, match='OpenAI 兼容协议'):
        review_schedule(_solution_two_math_same_day(), _dataset(), _cfg(), [], [])
