"""导入 / 配置相关的 REST 端点。"""
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from scheduler.core.calendar_import import CalendarParseError, parse_calendar_workbook
from scheduler.core.config import ConfigError, load_config
from scheduler.core.importer import (
    build_dataset_from_pivot, build_rules_sheet_template, import_rule_text_table,
    import_teaching_table, merge_teacher_facts_into_teaching_yaml,
    merge_teaching_and_rules, write_rules_generated_yaml_for_grade,
    write_rules_yaml, write_teaching_yaml,
)
from scheduler.core.models import Course, GradeCalendar, Teacher, Venue
from scheduler.core.rules import RULE_TYPES, Rule, RuleError

from . import sessions
from .schemas import (
    AiSettingsGetResponse, AiSettingsPutRequest,
    CalendarGetResponse, CalendarParseResponse, CalendarPutRequest,
    ConfigStatus, CourseItem, CoursesGetResponse, CoursesPutRequest,
    CrossGradeConflictItem, ExportAllCheckResponse, ExportAllRequest,
    GradeItem, GradesGetResponse, GradesPutRequest,
    ImportConfirmRequest, ImportConfirmResponse, ImportPreview,
    ImportSessionSummary, ImportSessionsListResponse, ParsedCalendarSheetItem,
    AlternatePairItem, AlternatePairsGetResponse, AlternatePairsPutRequest,
    PlanGetResponse, PlanPutRequest, RuleItem, RulesGetResponse, RulesPutRequest,
    RuleSheetParseResponse, RuleSheetPutRequest, RuleSheetPutResponse,
    TeachingTableEntry, TeachingTablePutRequest, TeachingTableResponse,
    VenueItem, VenuesGetResponse, VenuesPutRequest,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'

router = APIRouter(prefix='/api')


def _mask_key(key: str) -> str:
    """sk-…最后 4 位,前端用来确认「已配置」而非回显明文。"""
    return '%s…%s' % (key[:4], key[-4:]) if len(key) > 8 else '%s…' % key[:4]


@router.get('/settings/ai', response_model=AiSettingsGetResponse)
def get_ai_settings():
    """两个供应商的配置状态都要报——用户在两者之间切换时，界面得知道另一
    个供应商是不是已经配过了，不能只看当前选中的那个（见子项目8：两者
    并存，OpenAI 兼容协议为主，Anthropic 保留为可选项）。"""
    from scheduler.core import settings_store
    provider = settings_store.get_setting('ai.provider') or 'openai'

    openai_key = settings_store.get_setting('ai.openai.api_key')
    anthropic_local = settings_store.get_setting('ai.api_key')
    anthropic_env = os.environ.get('ANTHROPIC_API_KEY')

    return AiSettingsGetResponse(
        provider=provider,
        openai_configured=bool(openai_key),
        openai_base_url=settings_store.get_setting('ai.openai.base_url'),
        openai_model=settings_store.get_setting('ai.openai.model'),
        openai_masked_key=_mask_key(openai_key) if openai_key else None,
        anthropic_configured=bool(anthropic_local or anthropic_env),
        anthropic_source='local' if anthropic_local else ('env' if anthropic_env else 'none'),
        anthropic_masked_key=_mask_key(anthropic_local) if anthropic_local else None,
    )


@router.put('/settings/ai', response_model=dict)
def put_ai_settings(body: AiSettingsPutRequest):
    """只更新提交的那个供应商的字段——切换 provider 不会清空另一个供应商
    已经存好的凭据，回切回去时不用重新填。字段留空表示"不改这一项"
    （比如 API key 已经配过、这次只想改 base_url/model）。"""
    from scheduler.core import settings_store
    if body.provider not in ('openai', 'anthropic'):
        raise HTTPException(status_code=400, detail='未知的 AI 供应商：%r' % body.provider)
    settings_store.set_setting('ai.provider', body.provider)

    if body.provider == 'openai':
        if body.openai_base_url and body.openai_base_url.strip():
            settings_store.set_setting('ai.openai.base_url', body.openai_base_url.strip())
        if body.openai_api_key and body.openai_api_key.strip():
            settings_store.set_setting('ai.openai.api_key', body.openai_api_key.strip())
        if body.openai_model and body.openai_model.strip():
            settings_store.set_setting('ai.openai.model', body.openai_model.strip())
    else:
        if body.anthropic_api_key and body.anthropic_api_key.strip():
            settings_store.set_setting('ai.api_key', body.anthropic_api_key.strip())
    return {'ok': True}


@router.post('/settings/ai/test', response_model=dict)
def test_ai_settings():
    from scheduler.ai.client import AiConfigError, get_ai_client
    try:
        client = get_ai_client()
    except AiConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        client.complete('', 'ping', max_tokens=1)
    except Exception as exc:
        raise HTTPException(status_code=400,
                           detail='AI 连接失败：%s' % exc)
    return {'ok': True}


def _load_config_or_400():
    """`load_config` 在配置缺失/不自洽时抛 `ConfigError`——统一转成 400，
    不能让它裸传播成未格式化的 500。同时兜住 `yaml.YAMLError`：
    courses.yaml/venues.yaml/plans.yaml 任何一份语法损坏时，`load_config`
    内部对 YAML 的读取本身没有守卫（`core/config.py` 不在本轮改动范围内），
    这里统一收口，不让损坏的静态配置文件产生裸 500（见 finding I4）。"""
    try:
        return load_config(DEFAULT_CONFIG_DIR)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail='配置文件不是合法的 YAML：%s' % exc)


@router.post('/import', response_model=ImportPreview)
async def import_files(teaching_file: UploadFile = File(...),
                       rules_file: UploadFile = File(...),
                       grade: str = '初三', rule_engine: str = 'regex'):
    cfg = _load_config_or_400()
    with tempfile.TemporaryDirectory() as tmpdir:
        # 绝不能用客户端上传的文件名拼路径——那是攻击者可控字符串，
        # 塞入 `..` 段或绝对路径能让写入落到 tmpdir 之外。固定文件名，
        # 只保留后缀方便调试。
        teaching_suffix = Path(teaching_file.filename or '').suffix or '.xlsx'
        rules_suffix = Path(rules_file.filename or '').suffix or '.xlsx'
        teaching_path = Path(tmpdir) / f'teaching{teaching_suffix}'
        rules_path = Path(tmpdir) / f'rules{rules_suffix}'
        teaching_path.write_bytes(await teaching_file.read())
        rules_path.write_bytes(await rules_file.read())
        try:
            result = merge_teaching_and_rules(teaching_path, rules_path, cfg,
                                              grade=grade, rule_engine=rule_engine)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:   # AIParseError 等
            raise HTTPException(status_code=400, detail=str(exc))

    token = sessions.save_import(result, grade, rule_engine)
    return _build_import_preview(token, result, rule_engine)


def _build_import_preview(token: str, result, rule_engine: str) -> ImportPreview:
    used = {}
    for t in result.dataset.tasks:
        if t.consumes_slot:
            used[t.class_id] = used.get(t.class_id, 0) + t.periods
    return ImportPreview(
        token=token,
        teachers=len(result.dataset.teachers),
        classes=len(result.dataset.classes),
        tasks=len(result.dataset.tasks),
        occupancy=sorted(set(used.values())),
        rule_engine=rule_engine,
        rule_echo=result.rule_echo,
        warnings=result.warnings,
        conflicts=result.conflicts,
    )


@router.post('/import/confirm', response_model=ImportConfirmResponse)
def confirm_import(body: ImportConfirmRequest):
    session = sessions.get_import(body.token)
    if session is None:
        raise HTTPException(status_code=404, detail='导入会话不存在或已过期，请重新上传')
    if session.result.conflicts:
        raise HTTPException(status_code=400, detail='两份文件存在教师归属冲突，不能确认导入')

    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    rules_path = DEFAULT_CONFIG_DIR / 'rules.generated.yaml'
    write_teaching_yaml(session.result, teaching_path)
    write_rules_yaml(session.result, rules_path)
    return ImportConfirmResponse(ok=True, teaching_path=str(teaching_path),
                                 rules_path=str(rules_path))


@router.get('/imports', response_model=ImportSessionsListResponse)
def list_imports():
    return ImportSessionsListResponse(
        imports=[ImportSessionSummary(**row) for row in sessions.list_imports()])


@router.get('/imports/{token}', response_model=ImportPreview)
def get_import_detail(token: str):
    session = sessions.get_import(token)
    if session is None:
        raise HTTPException(status_code=404, detail='导入会话不存在或已过期')
    return _build_import_preview(token, session.result, session.rule_engine)


@router.delete('/imports/{token}')
def delete_import(token: str):
    if sessions.get_import(token) is None:
        raise HTTPException(status_code=404, detail='导入会话不存在或已过期')
    sessions.delete_import(token)
    return {'ok': True}


@router.delete('/imports')
def clear_imports():
    sessions.clear_imports()
    return {'ok': True}


def _load_yaml_dict_or_400(path: Path, what: str) -> dict:
    """读一份配置 YAML 并要求顶层是个 dict——解析失败或结构不对时转成干净的 400，

    不能让 yaml.YAMLError 或 dict 方法调用在非 dict 上炸出来的 AttributeError
    裸传播成没有诊断信息的 500（见 finding I4：这类文件损坏往往发生在
    /api/config/status，是前端加载页面的第一个请求，叠加 I1 会变成一片空白）。
    """
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail='%s 内容不是合法的 YAML：%s' % (what, exc))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400,
                           detail='%s 内容格式不对，顶层应为键值映射，实际是 %s'
                                  % (what, type(data).__name__))
    return data


@router.get('/config/status', response_model=ConfigStatus)
def config_status():
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if not teaching_path.exists():
        return ConfigStatus(ready=False)
    data = _load_yaml_dict_or_400(teaching_path, 'teaching.yaml')
    return ConfigStatus(ready=True, grade=data.get('grade'),
                        classes=len(data.get('classes', [])),
                        tasks=len(data.get('tasks', [])))


@router.get('/config/plan', response_model=PlanGetResponse)
def get_plan(grade: str = '初三'):
    cfg = _load_config_or_400()
    return PlanGetResponse(grade=grade, plan=cfg.plans.get(grade, {}),
                           reserved_slots=cfg.reserved_slots.get(grade, []))


@router.put('/config/plan', response_model=PlanGetResponse)
def put_plan(body: PlanPutRequest):
    cfg = _load_config_or_400()
    candidate = cfg.model_copy(deep=True)
    candidate.plans[body.grade] = body.plan
    try:
        candidate.validate_plan(body.grade)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    plans_path = DEFAULT_CONFIG_DIR / 'plans.yaml'
    raw = _load_yaml_dict_or_400(plans_path, 'plans.yaml')
    raw.setdefault('plans', {})[body.grade] = body.plan
    plans_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                          encoding='utf-8')
    return PlanGetResponse(grade=body.grade, plan=body.plan,
                           reserved_slots=cfg.reserved_slots.get(body.grade, []))


@router.get('/config/courses', response_model=CoursesGetResponse)
def get_courses(grade: str = '初三'):
    cfg = _load_config_or_400()
    return CoursesGetResponse(courses=[
        CourseItem(**c.model_dump()) for c in cfg.courses.get(grade, {}).values()
    ])


@router.get('/config/grades', response_model=GradesGetResponse)
def get_grades():
    cfg = _load_config_or_400()
    return GradesGetResponse(grades=[GradeItem(name=g.name, classes=g.classes) for g in cfg.grades])


@router.put('/config/grades', response_model=GradesGetResponse)
def put_grades(body: GradesPutRequest):
    names = [g.name.strip() for g in body.grades]
    if any(not n for n in names):
        raise HTTPException(status_code=400, detail='年级名不能为空')
    if len(names) != len(set(names)):
        dup = next(n for n in names if names.count(n) > 1)
        raise HTTPException(status_code=400, detail='年级名 %r 重复' % dup)
    if any(g.classes < 1 for g in body.grades):
        raise HTTPException(status_code=400, detail='班级数必须至少为 1')

    grades_path = DEFAULT_CONFIG_DIR / 'grades.yaml'
    grades_path.write_text(
        yaml.safe_dump({'grades': [{'name': n, 'classes': g.classes}
                                   for n, g in zip(names, body.grades)]},
                       allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    return GradesGetResponse(grades=[GradeItem(name=n, classes=g.classes)
                                     for n, g in zip(names, body.grades)])


@router.post('/config/calendars/parse', response_model=CalendarParseResponse)
async def parse_calendars(file: UploadFile = File(...)):
    with tempfile.TemporaryDirectory() as tmpdir:
        suffix = Path(file.filename or '').suffix or '.xlsx'
        path = Path(tmpdir) / f'calendar{suffix}'
        path.write_bytes(await file.read())
        try:
            sheets = parse_calendar_workbook(path)
        except CalendarParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return CalendarParseResponse(sheets=[
        ParsedCalendarSheetItem(**s.model_dump()) for s in sheets
    ])


@router.get('/config/calendars/{grade}', response_model=CalendarGetResponse)
def get_calendar(grade: str):
    cfg = _load_config_or_400()
    try:
        calendar = cfg.calendar_of(grade)
    except ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return CalendarGetResponse(grade=grade, days=calendar.days,
                               periods_per_day=calendar.periods_per_day,
                               midday_break_after=calendar.midday_break_after,
                               clock_times=calendar.clock_times or [])


@router.put('/config/calendars/{grade}', response_model=CalendarGetResponse)
def put_calendar(grade: str, body: CalendarPutRequest):
    try:
        GradeCalendar(days=body.days, periods_per_day=body.periods_per_day,
                     midday_break_after=body.midday_break_after,
                     clock_times=body.clock_times)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    calendars_path = DEFAULT_CONFIG_DIR / 'calendars.yaml'
    raw = _load_yaml_dict_or_400(calendars_path, 'calendars.yaml') if calendars_path.exists() else {}
    all_calendars = raw.setdefault('grade_calendars', {})
    existing = all_calendars.get(grade) or {}
    all_calendars[grade] = {
        'days': body.days,
        'periods_per_day': body.periods_per_day,
        'midday_break_after': body.midday_break_after,
        'clock_times': [list(t) for t in body.clock_times],
        'reserved_slots': existing.get('reserved_slots', []),
    }
    calendars_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                              encoding='utf-8')
    return CalendarGetResponse(grade=grade, days=body.days,
                               periods_per_day=body.periods_per_day,
                               midday_break_after=body.midday_break_after,
                               clock_times=body.clock_times)


@router.get('/config/venues', response_model=VenuesGetResponse)
def get_venues():
    cfg = _load_config_or_400()
    return VenuesGetResponse(venues=[
        VenueItem(**v.model_dump()) for v in cfg.venues.values()
    ])


@router.put('/config/venues', response_model=VenuesGetResponse)
def put_venues(body: VenuesPutRequest):
    """场地容量（数量）编辑。不允许删掉某个年级的课程还在引用的场地——
    那会在下次 load_config 时炸出『未声明的场地』，不如现在就拒绝。"""
    cfg = _load_config_or_400()
    names = {item.name for item in body.venues}
    if len(names) != len(body.venues):
        dup_list = [item.name for item in body.venues]
        dup = next(n for n in dup_list if dup_list.count(n) > 1)
        raise HTTPException(status_code=400, detail='场地名 %r 重复' % dup)

    still_referenced = {
        course.venue
        for grade_courses in cfg.courses.values()
        for course in grade_courses.values()
        if course.venue
    }
    missing = still_referenced - names
    if missing:
        raise HTTPException(status_code=400,
                           detail='场地 %s 仍被课程引用，不能删除' % '、'.join(sorted(missing)))

    venues_path = DEFAULT_CONFIG_DIR / 'venues.yaml'
    venues_path.write_text(
        yaml.safe_dump({'venues': [item.model_dump(exclude_defaults=True) for item in body.venues]},
                       allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    return VenuesGetResponse(venues=body.venues)


@router.get('/config/rules', response_model=RulesGetResponse)
def get_rules():
    """只读写 rules.yaml（手写的政策级规则），不碰 rules.generated.yaml——

    后者是导入器从 Excel 批量生成的 121 位教师的 forbid_slots，走的是导入
    确认流程，不该在这个通用规则编辑器里被当成"新增/删除一行"来操作。
    """
    rules_path = DEFAULT_CONFIG_DIR / 'rules.yaml'
    raw = _load_yaml_dict_or_400(rules_path, 'rules.yaml') if rules_path.exists() else {}
    return RulesGetResponse(rules=[RuleItem(**r) for r in raw.get('rules', [])],
                            rule_types=sorted(RULE_TYPES))


@router.put('/config/rules', response_model=RulesGetResponse)
def put_rules(body: RulesPutRequest):
    validated = []
    for item in body.rules:
        try:
            validated.append(Rule(**item.model_dump()).validate_type())
        except RuleError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    rules_path = DEFAULT_CONFIG_DIR / 'rules.yaml'
    rules_path.write_text(
        yaml.safe_dump({'rules': [r.model_dump(exclude_defaults=True) for r in validated]},
                       allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    return RulesGetResponse(rules=body.rules, rule_types=sorted(RULE_TYPES))


def _scan_alternate_pairs(path: Path, grade: str, courses: dict, editable: bool) -> list:
    if not path.exists():
        return []
    raw = _load_yaml_dict_or_400(path, path.name)
    out = []
    for r in raw.get('rules', []):
        if r.get('type') != 'alternate_weeks':
            continue
        if (r.get('scope') or {}).get('grade') != grade:
            continue
        pair = (r.get('params') or {}).get('pair') or []
        if len(pair) != 2:
            continue
        c1, c2 = pair
        course1, course2 = courses.get(c1), courses.get(c2)
        if course1 is None or course2 is None:
            continue
        if {course1.alternate, course2.alternate} != {'单周', '双周'}:
            continue   # 数据不自洽（比如课程目录已经改过但规则没跟上），跳过不展示
        single, double = (c1, c2) if course1.alternate == '单周' else (c2, c1)
        out.append(AlternatePairItem(family=course1.family, single_course=single,
                                     double_course=double, editable=editable))
    return out


@router.get('/config/alternate-pairs', response_model=AlternatePairsGetResponse)
def get_alternate_pairs(grade: str = '初三'):
    """单双周配对——从 rules.yaml（手写，可编辑）和 rules.generated.yaml
    （排课说明导入自动生成，只读展示）里找 alternate_weeks 规则，按课程目录
    里两门课各自的 alternate 字段区分哪门单周、哪门双周。"""
    cfg = _load_config_or_400()
    courses = cfg.courses.get(grade, {})
    pairs = (_scan_alternate_pairs(DEFAULT_CONFIG_DIR / 'rules.yaml', grade, courses, True)
            + _scan_alternate_pairs(DEFAULT_CONFIG_DIR / 'rules.generated.yaml', grade, courses, False))
    return AlternatePairsGetResponse(pairs=pairs)


@router.put('/config/alternate-pairs', response_model=AlternatePairsGetResponse)
def put_alternate_pairs(body: AlternatePairsPutRequest):
    """只管理手写的配对（写进 rules.yaml）——排课说明导入自动生成的那份
    （rules.generated.yaml）在这里只读展示，不受这个接口影响。"""
    cfg = _load_config_or_400()
    courses = cfg.courses.get(body.grade, {})

    seen_courses = set()
    for item in body.pairs:
        if item.single_course == item.double_course:
            raise HTTPException(status_code=400, detail='单周课程和双周课程不能是同一门课')
        for name in (item.single_course, item.double_course):
            if name not in courses:
                raise HTTPException(status_code=400,
                                   detail='课程 %r 不在 %s 的课程目录里' % (name, body.grade))
            if name in seen_courses:
                raise HTTPException(status_code=400, detail='课程 %r 被用在多个单双周配对里' % name)
            seen_courses.add(name)

    courses_raw = _load_yaml_dict_or_400(DEFAULT_CONFIG_DIR / 'courses.yaml', 'courses.yaml')
    grade_courses = courses_raw.setdefault('courses', {}).setdefault(body.grade, [])
    by_name = {c['name']: c for c in grade_courses}
    for item in body.pairs:
        if item.single_course in by_name:
            by_name[item.single_course]['family'] = item.family
            by_name[item.single_course]['alternate'] = '单周'
        if item.double_course in by_name:
            by_name[item.double_course]['family'] = item.family
            by_name[item.double_course]['alternate'] = '双周'
    (DEFAULT_CONFIG_DIR / 'courses.yaml').write_text(
        yaml.safe_dump({'courses': courses_raw['courses']}, allow_unicode=True, sort_keys=False),
        encoding='utf-8')

    rules_path = DEFAULT_CONFIG_DIR / 'rules.yaml'
    rules_raw = _load_yaml_dict_or_400(rules_path, 'rules.yaml') if rules_path.exists() else {}
    kept = [r for r in rules_raw.get('rules', [])
           if not (r.get('type') == 'alternate_weeks'
                   and (r.get('scope') or {}).get('grade') == body.grade)]
    for item in body.pairs:
        kept.append({
            'type': 'alternate_weeks',
            'scope': {'grade': body.grade},
            'params': {'pair': [item.single_course, item.double_course]},
            'mode': 'hard',
        })
    rules_path.write_text(yaml.safe_dump({'rules': kept}, allow_unicode=True, sort_keys=False),
                          encoding='utf-8')

    return get_alternate_pairs(body.grade)


def _teaching_table_shape(grade: str, cfg) -> Tuple[List[int], List[str]]:
    courses = [c.name for c in cfg.courses.get(grade, {}).values() if not c.external]
    grade_info = next((g for g in cfg.grades if g.name == grade), None)
    classes = list(range(1, grade_info.classes + 1)) if grade_info else []
    return classes, courses


def _load_existing_teachers(grade: str) -> Dict[str, Teacher]:
    """任课表导入/编辑不产生教师禁排、职务信息，必须沿用 teaching.yaml 里已有的，
    否则每次保存都会把排课说明.xlsx 导入算出来的这部分信息整体清空（见坑：
    浏览器实测中招过一次，编辑单个格子会把 121 位教师的 duties/forbidden 清空）。"""
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if not teaching_path.exists():
        return {}
    data = _load_yaml_dict_or_400(teaching_path, 'teaching.yaml')
    if data.get('grade') != grade:
        return {}
    return {t['name']: Teacher(**t) for t in data.get('teachers', [])}


@router.get('/config/teaching-table', response_model=TeachingTableResponse)
def get_teaching_table(grade: str = '初三'):
    """任课表是"谁教谁"的唯一来源——这里读的是已经确认导入的 teaching.yaml，
    不是排课说明.xlsx（那份降级为纯规则文本表，另一条路径处理）。"""
    cfg = _load_config_or_400()
    classes, courses = _teaching_table_shape(grade, cfg)

    entries: List[TeachingTableEntry] = []
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if teaching_path.exists():
        data = _load_yaml_dict_or_400(teaching_path, 'teaching.yaml')
        if data.get('grade') == grade:
            entries = [TeachingTableEntry(class_id=t['class_id'], course=t['course'], teacher=t['teacher'])
                      for t in data.get('tasks', [])]
    return TeachingTableResponse(classes=classes, courses=courses, entries=entries)


@router.post('/config/teaching-table/parse', response_model=TeachingTableResponse)
async def parse_teaching_table_upload(grade: str = '初三', file: UploadFile = File(...)):
    """上传后只解析、不落盘——预览页面确认无误再调 PUT 才真正写 teaching.yaml。"""
    cfg = _load_config_or_400()
    with tempfile.TemporaryDirectory() as tmpdir:
        suffix = Path(file.filename or '').suffix or '.xlsx'
        path = Path(tmpdir) / f'teaching_table{suffix}'
        path.write_bytes(await file.read())
        existing_teachers = _load_existing_teachers(grade)
        try:
            result = import_teaching_table(path, cfg, grade=grade, existing_teachers=existing_teachers)
        except (ValueError, ValidationError, ConfigError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    _, courses = _teaching_table_shape(grade, cfg)
    entries = [TeachingTableEntry(class_id=t.class_id, course=t.course, teacher=t.teacher)
              for t in result.dataset.tasks]
    return TeachingTableResponse(classes=result.dataset.classes, courses=courses,
                                 entries=entries, warnings=result.warnings)


@router.put('/config/teaching-table', response_model=TeachingTableResponse)
def put_teaching_table(body: TeachingTablePutRequest):
    """确认导入 / 编辑保存共用这一个入口——整份提交，覆盖式写 teaching.yaml。

    只碰 teaching.yaml，不碰 rules.generated.yaml——排课说明.xlsx 导入生成的
    教师禁排等规则不受这里影响（那是另一条导入路径的职责，子项目5）。
    """
    cfg = _load_config_or_400()
    pivot = {(e.class_id, e.course): e.teacher for e in body.entries}
    existing_teachers = _load_existing_teachers(body.grade)
    try:
        result = build_dataset_from_pivot(pivot, cfg, grade=body.grade, existing_teachers=existing_teachers)
    except (ValueError, ValidationError, ConfigError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    write_teaching_yaml(result, DEFAULT_CONFIG_DIR / 'teaching.yaml')

    _, courses = _teaching_table_shape(body.grade, cfg)
    entries = [TeachingTableEntry(class_id=t.class_id, course=t.course, teacher=t.teacher)
              for t in result.dataset.tasks]
    return TeachingTableResponse(classes=result.dataset.classes, courses=courses,
                                 entries=entries, warnings=result.warnings)


def _get_ai_client_or_none():
    """AI 复核是尽力而为、不是必需项——没配置 API key 时安静跳过，不报错
    （子项目5：正则结果永远是真正生效的规则，AI 只是"再捋一下"的第二意见）。"""
    from scheduler.core.settings_store import get_ai_api_key
    api_key = get_ai_api_key()
    if not api_key:
        return None
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


@router.get('/config/rules-sheet/template')
def get_rules_sheet_template():
    wb = build_rules_sheet_template()
    out_path = Path(tempfile.mkdtemp()) / '排课说明模板.xlsx'
    wb.save(out_path)
    return FileResponse(
        out_path,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=out_path.name,
    )


@router.post('/config/rules-sheet/parse', response_model=RuleSheetParseResponse)
async def parse_rules_sheet(grade: str = '初三', file: UploadFile = File(...)):
    """上传后只解析、不落盘——预览确认无误再调 PUT 才真正写 rules.generated.yaml
    和 teaching.yaml。正则结果永远算一遍；AI 客户端已配置时额外跑复核对比。"""
    cfg = _load_config_or_400()
    ai_client = _get_ai_client_or_none()
    with tempfile.TemporaryDirectory() as tmpdir:
        suffix = Path(file.filename or '').suffix or '.xlsx'
        path = Path(tmpdir) / f'rules{suffix}'
        path.write_bytes(await file.read())
        try:
            result = import_rule_text_table(path, cfg, grade=grade, ai_client=ai_client)
        except (ValueError, ValidationError, ConfigError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return RuleSheetParseResponse(grade=grade, rules=result.rules, teacher_facts=result.teacher_facts,
                                  warnings=result.warnings, rule_echo=result.rule_echo,
                                  ai_reviewed=ai_client is not None)


@router.put('/config/rules-sheet', response_model=RuleSheetPutResponse)
def put_rules_sheet(body: RuleSheetPutRequest):
    """确认导入——把预览页面已经算好的 rules/teacher_facts 写盘。
    rules.generated.yaml 按年级整体替换（其他年级不受影响）；teaching.yaml
    按教师姓名合并职务/禁排，没提到的教师原样保留（见 merge_teacher_facts_into_teaching_yaml）。
    """
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        merge_teacher_facts_into_teaching_yaml(
            body.teacher_facts, body.grade, DEFAULT_CONFIG_DIR / 'teaching.yaml')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    write_rules_generated_yaml_for_grade(
        body.rules, body.grade, DEFAULT_CONFIG_DIR / 'rules.generated.yaml')

    return RuleSheetPutResponse(ok=True, rules_written=len(body.rules),
                                teachers_updated=len(body.teacher_facts))


@router.put('/config/courses', response_model=CoursesGetResponse)
def put_courses(body: CoursesPutRequest):
    cfg = _load_config_or_400()

    names = [item.name for item in body.courses]
    if len(names) != len(set(names)):
        dup = next(n for n in names if names.count(n) > 1)
        raise HTTPException(status_code=400, detail='课程名 %r 重复' % dup)

    candidate = cfg.model_copy(deep=True)
    candidate.courses[body.grade] = {item.name: Course(**item.model_dump()) for item in body.courses}

    new_venues = {item.venue for item in body.courses
                  if item.venue and item.venue not in candidate.venues}
    for venue_name in new_venues:
        candidate.venues[venue_name] = Venue(name=venue_name)

    for grade in candidate.plans:
        try:
            candidate.validate_plan(grade)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    courses_raw = _load_yaml_dict_or_400(DEFAULT_CONFIG_DIR / 'courses.yaml', 'courses.yaml')
    courses_raw.setdefault('courses', {})[body.grade] = [
        item.model_dump(exclude_defaults=True) for item in body.courses]
    (DEFAULT_CONFIG_DIR / 'courses.yaml').write_text(
        yaml.safe_dump({'courses': courses_raw['courses']}, allow_unicode=True, sort_keys=False),
        encoding='utf-8')
    if new_venues:
        venues_raw = _load_yaml_dict_or_400(DEFAULT_CONFIG_DIR / 'venues.yaml', 'venues.yaml')
        venues_raw.setdefault('venues', []).extend(
            {'name': v} for v in sorted(new_venues))
        (DEFAULT_CONFIG_DIR / 'venues.yaml').write_text(
            yaml.safe_dump(venues_raw, allow_unicode=True, sort_keys=False),
            encoding='utf-8')

    return CoursesGetResponse(courses=body.courses)


# 模块级常量，方便测试用 monkeypatch 模拟『模板文件缺失』而不必真的动仓库根目录下
# 那份未纳入 git 管理的 课程表模板.xlsx（见 finding I3）。
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / '课程表模板.xlsx'


def _load_export_entries(selections):
    """按 (grade, job_id, candidate_index) 取出每个年级要导出的 (dataset, solution, cfg)。
    校验 job 存在、年级对得上、候选方案序号在范围内——都是用户能在 UI 里选错的
    地方，不能让下标越界之类的裸异常传播成 500。"""
    entries = {}
    for sel in selections:
        job = sessions.get_job(sel.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail='任务 %s 不存在' % sel.job_id)
        if job.grade != sel.grade:
            raise HTTPException(status_code=400,
                               detail='任务 %s 是 %s 的数据，不是请求里的 %s' % (sel.job_id, job.grade, sel.grade))
        if not 1 <= sel.candidate_index <= len(job.solutions):
            raise HTTPException(status_code=404,
                               detail='任务 %s 下没有候选方案 %d' % (sel.job_id, sel.candidate_index))
        entries[sel.grade] = (job.dataset, job.solutions[sel.candidate_index - 1], job.cfg)
    return entries


def _describe_cross_grade_conflict(c) -> str:
    return ('%s 在%s %s-%s 同时排了 %s%d班%s 和 %s%d班%s'
           % (c.teacher, c.day, c.start_a, c.end_a,
              c.grade_a, c.class_a, c.course_a, c.grade_b, c.class_b, c.course_b))


@router.post('/export/all/check', response_model=ExportAllCheckResponse)
def check_export_all(body: ExportAllRequest):
    """导出前的跨年级统一校验——只检查，不落盘。各年级独立求解，互不知道
    彼此，同一位教师可能被两个年级各自排到"同一时刻"，必须按真实钟点区间
    比对（不同年级作息形状可能不同，"第几节"不可比），见 cross_grade.py。"""
    from scheduler.core.cross_grade import find_cross_grade_conflicts

    entries = _load_export_entries(body.selections)
    conflicts, skipped = find_cross_grade_conflicts(
        {grade: (dataset, solution) for grade, (dataset, solution, _cfg) in entries.items()})
    return ExportAllCheckResponse(
        conflicts=[CrossGradeConflictItem(**c.model_dump()) for c in conflicts],
        skipped_grades=skipped)


@router.post('/export/all')
def export_all(body: ExportAllRequest):
    """确认校验通过后才真正导出——服务端重新校验一遍，不信任前端的"我已经
    check 过了"，避免前端跳过校验直接调这个接口拿到有冲突的课表。"""
    import zipfile

    from scheduler.core.cross_grade import find_cross_grade_conflicts
    from scheduler.core.exporter import export_excel

    entries = _load_export_entries(body.selections)
    conflicts, _skipped = find_cross_grade_conflicts(
        {grade: (dataset, solution) for grade, (dataset, solution, _cfg) in entries.items()})
    if conflicts:
        detail = ('跨年级校验未通过，存在 %d 处教师时间冲突，不能导出：%s'
                  % (len(conflicts), '；'.join(_describe_cross_grade_conflict(c) for c in conflicts[:5])))
        raise HTTPException(status_code=400, detail=detail)

    out_dir = Path(tempfile.mkdtemp())
    zip_path = out_dir / '全部课表.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for grade, (dataset, solution, cfg) in entries.items():
            xlsx_path = out_dir / ('%s.xlsx' % grade)
            export_excel(solution, dataset, xlsx_path, cfg=cfg)
            zf.write(xlsx_path, arcname='%s.xlsx' % grade)

    return FileResponse(zip_path, media_type='application/zip', filename='全部课表.zip')


@router.get('/export/{job_id}/{candidate_index}')
def export_candidate(job_id: str, candidate_index: int, template: int = 0):
    import tempfile

    from scheduler.core.exporter import export_excel, export_to_template

    job = sessions.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='任务不存在')
    if candidate_index < 1 or candidate_index > len(job.solutions):
        raise HTTPException(status_code=404, detail='该任务下没有这个候选方案')

    solution = job.solutions[candidate_index - 1]
    out_path = Path(tempfile.mkdtemp()) / ('候选%d.xlsx' % candidate_index)
    if template:
        if not TEMPLATE_PATH.exists():
            raise HTTPException(status_code=404,
                               detail='未找到课程表模板.xlsx，请把模板文件放在项目根目录')
        export_to_template(solution, job.dataset, TEMPLATE_PATH, out_path)
    else:
        export_excel(solution, job.dataset, out_path, cfg=job.cfg)
    return FileResponse(
        out_path,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=out_path.name,
    )
