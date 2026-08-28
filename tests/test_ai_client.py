"""AI 供应商抽象层（子项目8）：两处调用方（rule_parser.py/reviewer.py）
都通过 get_ai_client() 拿到一个只暴露 complete() 的统一接口。默认供应商
是 OpenAI 兼容协议，Anthropic 保留为可选项，两者的凭据分开存储，
切换供应商不会互相覆盖。
"""
import httpx
import pytest

from scheduler.ai.client import (
    AiConfigError, AnthropicAiClient, OpenAiCompatibleClient, get_ai_client,
)


def test_default_provider_is_openai_compatible_when_unset(monkeypatch):
    import scheduler.core.settings_store as store
    monkeypatch.setattr(store, 'get_setting', lambda key: {
        'ai.openai.base_url': 'https://example.com/v1',
        'ai.openai.api_key': 'sk-test',
        'ai.openai.model': 'gpt-test',
    }.get(key))
    client = get_ai_client()
    assert isinstance(client, OpenAiCompatibleClient)


def test_selecting_anthropic_provider_builds_an_anthropic_client(monkeypatch):
    import scheduler.core.settings_store as store
    monkeypatch.setattr(store, 'get_setting', lambda key: {
        'ai.provider': 'anthropic', 'ai.api_key': 'sk-ant-test',
    }.get(key))
    client = get_ai_client()
    assert isinstance(client, AnthropicAiClient)


def test_openai_provider_reports_exactly_which_fields_are_missing(monkeypatch):
    import scheduler.core.settings_store as store
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(store, 'get_setting', lambda key: {
        'ai.openai.base_url': 'https://example.com/v1',
    }.get(key))
    with pytest.raises(AiConfigError, match='API key.*模型名|模型名.*API key'):
        get_ai_client()


def test_anthropic_provider_raises_when_key_missing(monkeypatch):
    import scheduler.core.settings_store as store
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(store, 'get_setting', lambda key: (
        'anthropic' if key == 'ai.provider' else None))
    with pytest.raises(AiConfigError, match='Anthropic API key'):
        get_ai_client()


def test_openai_compatible_client_posts_to_chat_completions_and_parses_content(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return httpx.Response(200, json={'choices': [{'message': {'content': '你好'}}]},
                              request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', fake_post)
    client = OpenAiCompatibleClient(base_url='https://example.com/v1/', api_key='sk-test', model='gpt-test')
    result = client.complete('系统提示', '用户消息', max_tokens=99)

    assert result == '你好'
    assert captured['url'] == 'https://example.com/v1/chat/completions'
    assert captured['headers']['Authorization'] == 'Bearer sk-test'
    assert captured['json']['model'] == 'gpt-test'
    assert captured['json']['max_tokens'] == 99
    assert captured['json']['messages'] == [
        {'role': 'system', 'content': '系统提示'},
        {'role': 'user', 'content': '用户消息'},
    ]


def test_openai_compatible_client_raises_ai_config_error_on_http_failure(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        raise httpx.ConnectError('连不上')

    monkeypatch.setattr(httpx, 'post', fake_post)
    client = OpenAiCompatibleClient(base_url='https://example.com/v1', api_key='sk-test', model='gpt-test')
    with pytest.raises(AiConfigError, match='请求失败'):
        client.complete('系统提示', '用户消息')


def test_openai_compatible_client_raises_ai_config_error_on_malformed_response(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(200, json={'unexpected': 'shape'}, request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', fake_post)
    client = OpenAiCompatibleClient(base_url='https://example.com/v1', api_key='sk-test', model='gpt-test')
    with pytest.raises(AiConfigError, match='不满足格式'):
        client.complete('系统提示', '用户消息')
