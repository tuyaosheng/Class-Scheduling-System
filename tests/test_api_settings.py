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


def test_get_ai_settings_unconfigured():
    client = TestClient(app)
    resp = client.get('/api/settings/ai')
    assert resp.status_code == 200
    body = resp.json()
    assert body == {'configured': False, 'source': 'none', 'masked_key': None}


def test_put_then_get_shows_local_source_and_masked_key():
    client = TestClient(app)
    resp = client.put('/api/settings/ai', json={'api_key': 'sk-super-secret-abcdef'})
    assert resp.status_code == 200
    assert resp.json() == {'ok': True}

    resp = client.get('/api/settings/ai')
    body = resp.json()
    assert body['configured'] is True
    assert body['source'] == 'local'
    # 绝不回显完整 key
    assert 'sk-super-secret-abcdef' not in body['masked_key']
    assert body['masked_key'] == 'sk-s…cdef'


def test_put_blank_key_returns_400():
    client = TestClient(app)
    resp = client.put('/api/settings/ai', json={'api_key': '   '})
    assert resp.status_code == 400


def test_env_source_shown_when_only_env(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-env-only')
    client = TestClient(app)
    resp = client.get('/api/settings/ai')
    body = resp.json()
    assert body['configured'] is True
    assert body['source'] == 'env'
    assert body['masked_key'] is None


def test_test_endpoint_400_when_no_key():
    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 400


def test_test_endpoint_200_when_key_valid(monkeypatch):
    store.set_setting('ai.api_key', 'sk-valid')
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return object()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic, 'Anthropic', FakeAnthropic)

    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 200
    assert resp.json() == {'ok': True}
    assert calls and calls[0]['model'] == 'claude-sonnet-4-5'


def test_test_endpoint_400_when_call_fails(monkeypatch):
    store.set_setting('ai.api_key', 'sk-bad')

    class BrokenMessages:
        def create(self, **kwargs):
            raise RuntimeError('401 未授权')

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = BrokenMessages()

    monkeypatch.setattr(anthropic, 'Anthropic', FakeAnthropic)

    client = TestClient(app)
    resp = client.post('/api/settings/ai/test')
    assert resp.status_code == 400
    assert '401 未授权' in resp.json()['detail']


# ---------------------------------------------------------------- rule_parser 集成


def test_default_client_uses_local_key(monkeypatch):
    store.set_setting('ai.api_key', 'sk-local-client')
    client = _default_client()
    assert client is not None


def test_default_client_raises_when_no_key():
    with pytest.raises(Exception, match='API key'):
        _default_client()
