"""settings_store 单测 + /api/settings/ai 端点测试。

所有测试都 monkeypatch settings_store.DB_PATH 到临时目录,确保不受真实
开发机 ~/.scheduler/scheduler.db 影响。
"""
import anthropic
import pytest
from fastapi.testclient import TestClient

import scheduler.core.settings_store as store
from scheduler.ai.rule_parser import _default_client
from scheduler.api.app import app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """每个测试都用独立数据库文件,并清掉环境变量,保证确定性。"""
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)


# ---------------------------------------------------------------- settings_store 单元


def test_set_get_roundtrip():
    store.set_setting('ai.api_key', 'sk-test-123')
    assert store.get_setting('ai.api_key') == 'sk-test-123'


def test_get_missing_returns_none():
    assert store.get_setting('no_such_key') is None


def test_delete_removes_key():
    store.set_setting('ai.api_key', 'sk-x')
    store.delete_setting('ai.api_key')
    assert store.get_setting('ai.api_key') is None


def test_get_ai_api_key_prefers_local_over_env(monkeypatch):
    store.set_setting('ai.api_key', 'sk-local')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env')
    assert store.get_ai_api_key() == 'sk-local'


def test_get_ai_api_key_falls_back_to_env(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env')
    assert store.get_ai_api_key() == 'sk-env'


def test_get_ai_api_key_none_when_both_empty():
    assert store.get_ai_api_key() is None


# ---------------------------------------------------------------- 端点
#
# 子项目8：两个供应商并存，OpenAI 兼容协议为主（默认 provider），Anthropic
# 保留为可选项。GET 要同时报两边的配置状态——用户切换 provider 时界面得
# 知道"另一个供应商是不是已经配过了"，不能只看当前选中的那个。


def test_get_ai_settings_unconfigured():
    client = TestClient(app)
    resp = client.get('/api/settings/ai')
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        'provider': 'openai', 'openai_configured': False, 'openai_base_url': None,
        'openai_model': None, 'openai_masked_key': None, 'anthropic_configured': False,
        'anthropic_source': 'none', 'anthropic_masked_key': None,
    }


def test_put_openai_fields_then_get_reflects_them():
    client = TestClient(app)
    resp = client.put('/api/settings/ai', json={
        'provider': 'openai', 'openai_base_url': 'https://example.com/v1',
        'openai_api_key': 'sk-super-secret-abcdef', 'openai_model': 'gpt-test',
    })
    assert resp.status_code == 200
    assert resp.json() == {'ok': True}

    body = client.get('/api/settings/ai').json()
    assert body['provider'] == 'openai'
    assert body['openai_configured'] is True
    assert body['openai_base_url'] == 'https://example.com/v1'
    assert body['openai_model'] == 'gpt-test'
    assert 'sk-super-secret-abcdef' not in body['openai_masked_key']
    assert body['openai_masked_key'] == 'sk-s…cdef'


def test_switching_to_anthropic_does_not_wipe_saved_openai_config():
    client = TestClient(app)
    client.put('/api/settings/ai', json={
        'provider': 'openai', 'openai_base_url': 'https://example.com/v1',
        'openai_api_key': 'sk-openai-key', 'openai_model': 'gpt-test',
    })
    resp = client.put('/api/settings/ai', json={'provider': 'anthropic', 'anthropic_api_key': 'sk-ant-key'})
    assert resp.status_code == 200

    body = client.get('/api/settings/ai').json()
    assert body['provider'] == 'anthropic'
    assert body['anthropic_configured'] is True
    assert body['anthropic_source'] == 'local'
    # 切换供应商没有清空之前存好的 openai 配置——回切回去不用重新填。
    assert body['openai_configured'] is True
    assert body['openai_base_url'] == 'https://example.com/v1'


def test_put_unknown_provider_returns_400():
    client = TestClient(app)
    resp = client.put('/api/settings/ai', json={'provider': 'not-a-real-provider'})
    assert resp.status_code == 400


def test_env_source_shown_when_only_anthropic_env_is_set(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env-only')
    client = TestClient(app)
    body = client.get('/api/settings/ai').json()
    assert body['anthropic_configured'] is True
    assert body['anthropic_source'] == 'env'
    assert body['anthropic_masked_key'] is None


def test_test_endpoint_400_when_nothing_configured():
    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 400


def test_test_endpoint_200_when_openai_compatible_config_valid(monkeypatch):
    store.set_setting('ai.openai.base_url', 'https://example.com/v1')
    store.set_setting('ai.openai.api_key', 'sk-valid')
    store.set_setting('ai.openai.model', 'gpt-test')

    import httpx

    def fake_post(url, headers=None, json=None, timeout=None):
        return httpx.Response(200, json={'choices': [{'message': {'content': 'pong'}}]},
                              request=httpx.Request('POST', url))

    monkeypatch.setattr(httpx, 'post', fake_post)

    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 200
    assert resp.json() == {'ok': True}


def test_test_endpoint_400_when_openai_call_fails(monkeypatch):
    store.set_setting('ai.openai.base_url', 'https://example.com/v1')
    store.set_setting('ai.openai.api_key', 'sk-bad')
    store.set_setting('ai.openai.model', 'gpt-test')

    import httpx

    def fake_post(url, headers=None, json=None, timeout=None):
        raise httpx.ConnectError('连不上')

    monkeypatch.setattr(httpx, 'post', fake_post)

    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 400


def test_test_endpoint_200_when_anthropic_selected_and_valid(monkeypatch):
    store.set_setting('ai.provider', 'anthropic')
    store.set_setting('ai.api_key', 'sk-valid')
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return type('R', (), {'content': [type('C', (), {'text': 'pong'})()]})()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, 'Anthropic', FakeAnthropic)

    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 200
    assert calls and calls[0]['model'] == 'claude-sonnet-4-5'


# ---------------------------------------------------------------- rule_parser 集成


def test_default_client_uses_configured_openai_settings():
    store.set_setting('ai.openai.base_url', 'https://example.com/v1')
    store.set_setting('ai.openai.api_key', 'sk-local-client')
    store.set_setting('ai.openai.model', 'gpt-test')
    client = _default_client()
    assert client is not None


def test_default_client_raises_when_nothing_configured():
    with pytest.raises(Exception, match='OpenAI 兼容协议'):
        _default_client()
