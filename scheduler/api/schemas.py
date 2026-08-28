"""API 请求/响应模型——只用于 HTTP 边界，不与 scheduler.core.models 混用。"""
from typing import Dict, List, Optional, Tuple

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


class RuleTextEchoItem(BaseModel):
    raw: str
    parsed: str
    ai_parsed: Optional[str] = None
    mismatch: bool = False


class RuleSheetParseResponse(BaseModel):
    grade: str
    rules: List[dict]
    teacher_facts: List[dict]
    warnings: List[str]
    rule_echo: Dict[str, List[RuleTextEchoItem]]
    ai_reviewed: bool


class RuleSheetPutRequest(BaseModel):
    grade: str
    rules: List[dict]
    teacher_facts: List[dict]


class RuleSheetPutResponse(BaseModel):
    ok: bool
    rules_written: int
    teachers_updated: int


class ExportSelectionItem(BaseModel):
    grade: str
    job_id: str
    candidate_index: int


class ExportAllRequest(BaseModel):
    selections: List[ExportSelectionItem]


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


class SolveJobSummary(BaseModel):
    job_id: str
    status: str
    grade: str
    created_at: str
    candidate_count: int


class SolveJobsListResponse(BaseModel):
    jobs: List[SolveJobSummary]


class ImportSessionSummary(BaseModel):
    token: str
    grade: str
    created_at: str


class ImportSessionsListResponse(BaseModel):
    imports: List[ImportSessionSummary]


class CandidateItem(BaseModel):
    index: int
    status: str
    wall_time: float
    objective: Optional[float] = None
    stats: str = ''
    violations: List[dict]
    placements: List[dict]


class SolveJobDetail(BaseModel):
    job_id: str
    status: str
    grade: str
    candidates: List[CandidateItem]
    issues: List[dict] = []
    conflict: Optional[str] = None


class MoveItem(BaseModel):
    task_id: int
    from_slot: int
    to_slot: int


class AdjustRequest(BaseModel):
    class_id: int
    moves: List[MoveItem]


class RevertedMoveItem(BaseModel):
    task_id: int
    from_slot: int
    reason: str
    kinds: List[str] = []


class AdjustResponse(BaseModel):
    applied: List[MoveItem]
    reverted: List[RevertedMoveItem]
    placements: List[dict]


class AiSettingsGetResponse(BaseModel):
    provider: str
    openai_configured: bool
    openai_base_url: Optional[str] = None
    openai_model: Optional[str] = None
    openai_masked_key: Optional[str] = None
    anthropic_configured: bool
    anthropic_source: str
    anthropic_masked_key: Optional[str] = None


class AiSettingsPutRequest(BaseModel):
    provider: str
    openai_base_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    anthropic_api_key: Optional[str] = None


class CourseItem(BaseModel):
    name: str
    family: str
    venue: Optional[str] = None
    alternate: Optional[str] = None   # '单周' | '双周' | None
    external: bool = False            # 占位符 / 教务固定安排


class CoursesGetResponse(BaseModel):
    courses: List[CourseItem]


class CoursesPutRequest(BaseModel):
    grade: str
    courses: List[CourseItem]


class VenueItem(BaseModel):
    name: str
    capacity: Optional[int] = None


class VenuesGetResponse(BaseModel):
    venues: List[VenueItem]


class VenuesPutRequest(BaseModel):
    venues: List[VenueItem]


class FindingItem(BaseModel):
    severity: str
    scope: Dict = {}
    issue: str
    suggestion: str = ''


class ReviewResponse(BaseModel):
    findings: List[FindingItem]


class RuleItem(BaseModel):
    type: str
    scope: Dict = {}
    params: Dict = {}
    mode: str = 'hard'
    enabled: bool = True
    weight: int = 0
    description: str = ''


class RulesGetResponse(BaseModel):
    rules: List[RuleItem]
    rule_types: List[str]


class RulesPutRequest(BaseModel):
    rules: List[RuleItem]


class AlternatePairItem(BaseModel):
    family: str
    single_course: str
    double_course: str
    editable: bool = True   # False = 来自排课说明导入自动生成，只读展示，不在这里编辑


class AlternatePairsGetResponse(BaseModel):
    pairs: List[AlternatePairItem]


class AlternatePairsPutRequest(BaseModel):
    grade: str
    pairs: List[AlternatePairItem]


class TeachingTableEntry(BaseModel):
    class_id: int
    course: str
    teacher: str


class TeachingTableResponse(BaseModel):
    classes: List[int]
    courses: List[str]
    entries: List[TeachingTableEntry]
    warnings: List[str] = []


class TeachingTablePutRequest(BaseModel):
    grade: str
    entries: List[TeachingTableEntry]


class GradeItem(BaseModel):
    name: str
    classes: int


class GradesGetResponse(BaseModel):
    grades: List[GradeItem]


class GradesPutRequest(BaseModel):
    grades: List[GradeItem]


class ParsedCalendarSheetItem(BaseModel):
    sheet_name: str
    periods_per_day: int
    midday_break_after: int
    clock_times: List[Tuple[str, str]]


class CalendarParseResponse(BaseModel):
    sheets: List[ParsedCalendarSheetItem]


class CalendarGetResponse(BaseModel):
    grade: str
    days: List[str]
    periods_per_day: int
    midday_break_after: int
    clock_times: List[Tuple[str, str]]


class CalendarPutRequest(BaseModel):
    days: List[str] = ['周一', '周二', '周三', '周四', '周五']
    periods_per_day: int
    midday_break_after: int
    clock_times: List[Tuple[str, str]]
