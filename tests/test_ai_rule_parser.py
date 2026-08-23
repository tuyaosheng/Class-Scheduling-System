import json
from types import SimpleNamespace

import pytest

from scheduler.ai.rule_parser import AIParseError, ParsedRow, parse_row_ai


class FakeMessages:
    def __init__(self, text):
        self._text = text

    def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text=self._text)])


class FakeClient:
    def __init__(self, text):
        self.messages = FakeMessages(text)


def test_parses_valid_json_into_parsed_row():
    payload = {
        "not_available": [[3, 6], [3, 7]],
        "fixed_slots": [[1, 9]],
        "requirement": [{"type": "daily_min", "params": {"n": 1}}],
        "remark": [],
    }
    client = FakeClient(json.dumps(payload))
    result = parse_row_ai("周四下午不排课", "周二第9节", "保证每天有1节", "", client=client)
    assert isinstance(result, ParsedRow)
    assert result.not_available == [[3, 6], [3, 7]]
    assert result.fixed_slots == [[1, 9]]
    assert result.requirement == [{"type": "daily_min", "params": {"n": 1}}]
    assert result.remark == []


def test_raises_on_malformed_json():
    client = FakeClient("这不是 JSON")
    with pytest.raises(AIParseError, match="解析失败"):
        parse_row_ai("", "", "", "", client=client)


def test_raises_on_unknown_rule_type():
    payload = {
        "not_available": [], "fixed_slots": [],
        "requirement": [{"type": "fly_to_moon", "params": {}}],
        "remark": [],
    }
    client = FakeClient(json.dumps(payload))
    with pytest.raises(AIParseError, match="未知规则类型"):
        parse_row_ai("", "", "", "", client=client)


def test_raises_when_client_call_fails():
    class BrokenMessages:
        def create(self, **kwargs):
            raise ConnectionError("网络不通")

    class BrokenClient:
        messages = BrokenMessages()

    with pytest.raises(AIParseError, match="解析失败"):
        parse_row_ai("", "", "", "", client=BrokenClient())


def test_raises_on_missing_api_key(monkeypatch):
    """缺 key 应抛 AIParseError 而非 KeyError——本地设置与环境变量都为空时。

    不能只删环境变量:get_ai_api_key 会回退到本机 SQLite,测试必须把两路都
    隔离掉,否则会受真实开发机配置影响。
    """
    import scheduler.core.settings_store as store
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(store, 'get_setting', lambda key: None)
    with pytest.raises(AIParseError, match="API key"):
        parse_row_ai("", "", "", "")
