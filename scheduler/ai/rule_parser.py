"""AI 规则解析：把排课说明里的中文规则文本解析成结构化片段。

与 scheduler/core/ruletext.py（正则解析）产出同一种语义内容，供导入合并
逻辑按 rule_engine 参数二选一调用；解析结果照样要走人工回显确认——
AI 只负责「这句话是什么规则」的翻译，不做任何硬性判定（CLAUDE.md 铁律 5）。
"""
import json
from typing import Dict, List

from pydantic import BaseModel, Field, ValidationError

from scheduler.core.rules import RULE_TYPES

_SYSTEM_PROMPT = (
    "你是中小学排课系统的规则文本解析器。你会收到教务 Excel 里一位教师的四段"
    "中文自然语言文本（不能排课节次/固定节次/排课要求/备注），任务是把它们"
    "翻译成结构化 JSON，不做任何排课决策，只做文本理解与格式转换。"
    "时间格式：星期用 0-4（0=周一...4=周五），节次用 1-9（下午第N节=第5+N节，"
    "第9节是下午第4节）。只返回 JSON 本体，不要任何解释文字、不要代码块标记。"
)

_USER_TEMPLATE = (
    "不能排课节次：{not_available}\n"
    "固定节次：{fixed_slots}\n"
    "排课要求：{requirement}\n"
    "备注：{remark}\n\n"
    "返回 JSON，字段：\n"
    'not_available: [[星期,节次], ...]（该教师这些节次都不能排课）\n'
    'fixed_slots: [[星期,节次], ...]（该教师的课固定在这些节次的窗口内）\n'
    'requirement: [{{"type": 规则类型, "params": {{...}}}}, ...]\n'
    'remark: 同 requirement 的格式\n'
    "type 只能是以下之一：{rule_types}"
)


class ParsedRow(BaseModel):
    not_available: List[List[int]] = Field(default_factory=list)
    fixed_slots: List[List[int]] = Field(default_factory=list)
    requirement: List[Dict] = Field(default_factory=list)
    remark: List[Dict] = Field(default_factory=list)


class AIParseError(RuntimeError):
    """AI 解析失败：网络错误、超时，或返回内容不满足 schema。"""


def _default_client():
    from scheduler.ai.client import AiConfigError, get_ai_client
    try:
        return get_ai_client()
    except AiConfigError as exc:
        raise AIParseError(str(exc)) from exc


def parse_row_ai(not_available_text, fixed_slots_text, requirement_text, remark_text,
                 *, client=None) -> ParsedRow:
    try:
        client = client or _default_client()
        prompt = _USER_TEMPLATE.format(
            not_available=not_available_text or "（空）",
            fixed_slots=fixed_slots_text or "（空）",
            requirement=requirement_text or "（空）",
            remark=remark_text or "（空）",
            rule_types=sorted(RULE_TYPES),
        )
        raw_text = client.complete(_SYSTEM_PROMPT, prompt, max_tokens=1024)
    except AIParseError:
        raise
    except Exception as exc:
        raise AIParseError("AI 解析失败：%s，可切换为正则引擎重试" % exc) from exc

    try:
        data = json.loads(raw_text)
        parsed = ParsedRow(**data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise AIParseError("AI 解析失败：返回内容不满足格式，可切换为正则引擎重试") from exc

    for frag in parsed.requirement + parsed.remark:
        if frag.get("type") not in RULE_TYPES:
            raise AIParseError("AI 解析失败：返回了未知规则类型 %r" % frag.get("type"))
    return parsed
