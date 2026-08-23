"""API 请求/响应模型——只用于 HTTP 边界，不与 scheduler.core.models 混用。"""
from typing import Dict, List, Optional

from pydantic import BaseModel


class RuleEchoItem(BaseModel):
    raw: str
    parsed: str


class ImportPreview(BaseModel):
    token: str
    teachers: int
    classes: int
    tasks: int
    occupancy: List[int]
    rule_engine: str
    rule_echo: Dict[str, List[RuleEchoItem]]
    warnings: List[str]
    conflicts: List[dict]


class ImportConfirmRequest(BaseModel):
    token: str


class ImportConfirmResponse(BaseModel):
    ok: bool
    teaching_path: str
    rules_path: str


class ConfigStatus(BaseModel):
    ready: bool
    grade: Optional[str] = None
    classes: int = 0
    tasks: int = 0


class PlanGetResponse(BaseModel):
    grade: str
    plan: Dict[str, int]
    reserved_slots: List[List[int]]


class PlanPutRequest(BaseModel):
    grade: str
    plan: Dict[str, int]


class SolveRequest(BaseModel):
    grade: str = '初三'
    count: int = 3
    min_diff: int = 8
    max_seconds: int = 60


class SolveJobCreated(BaseModel):
    job_id: str


class AiSettingsGetResponse(BaseModel):
    configured: bool
    source: str
    masked_key: Optional[str] = None


class AiSettingsPutRequest(BaseModel):
    api_key: str


class CourseItem(BaseModel):
    name: str
    family: str
    venue: Optional[str] = None
    alternate: Optional[str] = None   # '单周' | '双周' | None
    external: bool = False            # 占位符 / 教务固定安排


class CoursesGetResponse(BaseModel):
    courses: List[CourseItem]


class CoursesPutRequest(BaseModel):
    courses: List[CourseItem]
