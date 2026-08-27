"""导入 / 配置相关的 REST 端点。"""
import os
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from scheduler.core.calendar_import import CalendarParseError, parse_calendar_workbook
from scheduler.core.config import ConfigError, load_config
from scheduler.core.importer import (
    merge_teaching_and_rules, write_rules_yaml, write_teaching_yaml,
)
from scheduler.core.models import Course, GradeCalendar, Venue
from scheduler.core.rules import RULE_TYPES, Rule, RuleError

from . import sessions
from .schemas import (
    AiSettingsGetResponse, AiSettingsPutRequest,
    CalendarGetResponse, CalendarParseResponse, CalendarPutRequest,
    ConfigStatus, CourseItem, CoursesGetResponse, CoursesPutRequest,
    GradeItem, GradesGetResponse, GradesPutRequest,
    ImportConfirmRequest, ImportConfirmResponse, ImportPreview,
    ImportSessionSummary, ImportSessionsListResponse, ParsedCalendarSheetItem,
    AlternatePairItem, AlternatePairsGetResponse, AlternatePairsPutRequest,
    PlanGetResponse, PlanPutRequest, RuleItem, RulesGetResponse, RulesPutRequest,
    VenueItem, VenuesGetResponse, VenuesPutRequest,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'

router = APIRouter(prefix='/api')


def _mask_key(key: str) -> str:
    """sk-…最后 4 位,前端用来确认「已配置」而非回显明文。"""
    return '%s…%s' % (key[:4], key[-4:]) if len(key) > 8 else '%s…' % key[:4]


@router.get('/settings/ai', response_model=AiSettingsGetResponse)
def get_ai_settings():
    from scheduler.core import settings_store
    local = settings_store.get_setting('ai.api_key')
    env = os.environ.get('ANTHROPIC_API_KEY')
    if local:
        return AiSettingsGetResponse(configured=True, source='local',
                                     masked_key=_mask_key(local))
    if env:
        return AiSettingsGetResponse(configured=True, source='env')
    return AiSettingsGetResponse(configured=False, source='none')


@router.put('/settings/ai', response_model=dict)
def put_ai_settings(body: AiSettingsPutRequest):
    from scheduler.core import settings_store
    key = body.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail='API key 不能为空')
    settings_store.set_setting('ai.api_key', key)
    return {'ok': True}


@router.post('/settings/ai/test', response_model=dict)
def test_ai_settings():
    from scheduler.core.settings_store import get_ai_api_key
    api_key = get_ai_api_key()
    if not api_key:
        raise HTTPException(status_code=400,
                           detail='未配置 API key：请先在「设置 → AI 设置」里填写')
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model='claude-sonnet-4-5', max_tokens=1,
            messages=[{'role': 'user', 'content': 'ping'}],
        )
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


from fastapi.responses import FileResponse

# 模块级常量，方便测试用 monkeypatch 模拟『模板文件缺失』而不必真的动仓库根目录下
# 那份未纳入 git 管理的 课程表模板.xlsx（见 finding I3）。
TEMPLATE_PATH = Path(__file__).resolve().parents[2] / '课程表模板.xlsx'


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
