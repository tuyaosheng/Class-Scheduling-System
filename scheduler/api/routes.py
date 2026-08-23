"""导入 / 配置相关的 REST 端点。"""
import os
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from scheduler.core.config import ConfigError, load_config
from scheduler.core.importer import (
    merge_teaching_and_rules, write_rules_yaml, write_teaching_yaml,
)
from scheduler.core.models import Course, Venue

from . import sessions
from .schemas import (
    AiSettingsGetResponse, AiSettingsPutRequest,
    ConfigStatus, CourseItem, CoursesGetResponse, CoursesPutRequest,
    ImportConfirmRequest, ImportConfirmResponse, ImportPreview,
    PlanGetResponse, PlanPutRequest,
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

    token = sessions.save_import(result, grade)
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
def get_courses():
    cfg = _load_config_or_400()
    return CoursesGetResponse(courses=[
        CourseItem(**c.model_dump()) for c in cfg.courses.values()
    ])


@router.put('/config/courses', response_model=CoursesGetResponse)
def put_courses(body: CoursesPutRequest):
    cfg = _load_config_or_400()

    names = [item.name for item in body.courses]
    if len(names) != len(set(names)):
        dup = next(n for n in names if names.count(n) > 1)
        raise HTTPException(status_code=400, detail='课程名 %r 重复' % dup)

    candidate = cfg.model_copy(deep=True)
    candidate.courses = {item.name: Course(**item.model_dump()) for item in body.courses}

    new_venues = {item.venue for item in body.courses
                  if item.venue and item.venue not in candidate.venues}
    for venue_name in new_venues:
        candidate.venues[venue_name] = Venue(name=venue_name)

    for grade in candidate.plans:
        try:
            candidate.validate_plan(grade)
        except ConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    courses_path = DEFAULT_CONFIG_DIR / 'courses.yaml'
    courses_path.write_text(
        yaml.safe_dump({'courses': [item.model_dump(exclude_defaults=True) for item in body.courses]},
                       allow_unicode=True, sort_keys=False),
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
