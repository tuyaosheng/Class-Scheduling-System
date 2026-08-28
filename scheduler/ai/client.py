"""AI 供应商抽象层。

`ai/rule_parser.py`（规则文本解析）和 `ai/reviewer.py`（课表审核）两处
调用方都通过这一层拿到一个只暴露 `complete(system, user)` 的统一接口，
不直接依赖某个供应商的 SDK/协议形状——这样切换供应商只用改这一个文件。

两者并存，**OpenAI 兼容协议为主**（用户自填 base_url + api_key + 模型名，
用纯 HTTP 调 `{base_url}/chat/completions`，不引入 openai SDK 依赖——
“OpenAI 兼容”的服务五花八门，直接打标准 HTTP 端点比依赖某个 SDK 的
客户端行为更稳），Anthropic 保留为可选项（继续用 anthropic SDK）。

`get_setting`/`get_ai_api_key` 的既有语义不变：`ai.api_key` 历史上就是
"Anthropic 的 key"（曾经是唯一供应商），这里不改名、不做数据迁移，
只是新增 openai 专属的几个 key，两个供应商的凭据分开存，切换供应商
不会互相覆盖。
"""
import os

import httpx


class AiConfigError(RuntimeError):
    """未配置或配置不完整——调用方统一转成"请去设置里配置"这一类用户可读提示。"""


class AnthropicAiClient:
    def __init__(self, api_key: str, model: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        response = self._client.messages.create(
            model=self._model, max_tokens=max_tokens, system=system,
            messages=[{'role': 'user', 'content': user}],
        )
        return response.content[0].text


class OpenAiCompatibleClient:
    """纯 HTTP 调用 `{base_url}/chat/completions`——标准 OpenAI 协议形状，
    绝大多数"OpenAI 兼容"的第三方/自建服务都是照这个形状实现的。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._model = model

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        try:
            resp = httpx.post(
                '%s/chat/completions' % self._base_url,
                headers={'Authorization': 'Bearer %s' % self._api_key},
                json={
                    'model': self._model,
                    'max_tokens': max_tokens,
                    'messages': [
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': user},
                    ],
                },
                timeout=60,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AiConfigError('OpenAI 兼容协议请求失败：%s' % exc) from exc
        try:
            return resp.json()['choices'][0]['message']['content']
        except (KeyError, IndexError, ValueError) as exc:
            raise AiConfigError('OpenAI 兼容协议返回内容不满足格式：%s' % exc) from exc


def get_ai_client():
    """按「设置 → AI 设置」里选定的供应商构造客户端；未配置完整时抛
    AiConfigError，调用方统一处理成用户可读提示，不裸传播 SDK 异常。"""
    from scheduler.core import settings_store

    provider = settings_store.get_setting('ai.provider') or 'openai'
    if provider == 'anthropic':
        api_key = settings_store.get_ai_api_key()
        if not api_key:
            raise AiConfigError('未配置 Anthropic API key：请在「设置 → AI 设置」里填写，'
                               '或设置环境变量 ANTHROPIC_API_KEY')
        model = settings_store.get_setting('ai.anthropic.model') or 'claude-sonnet-4-5'
        return AnthropicAiClient(api_key=api_key, model=model)

    base_url = settings_store.get_setting('ai.openai.base_url')
    api_key = settings_store.get_setting('ai.openai.api_key') or os.environ.get('OPENAI_API_KEY')
    model = settings_store.get_setting('ai.openai.model')
    missing = [label for label, value in
              (('base_url', base_url), ('API key', api_key), ('模型名', model)) if not value]
    if missing:
        raise AiConfigError('OpenAI 兼容协议未配置完整（缺少 %s）：请在「设置 → AI 设置」里填写'
                           % '、'.join(missing))
    return OpenAiCompatibleClient(base_url=base_url, api_key=api_key, model=model)
