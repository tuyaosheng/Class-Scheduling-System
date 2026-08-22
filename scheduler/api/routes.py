"""导入 / 配置相关的 REST 端点。"""
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import ValidationError

from scheduler.core.config import ConfigError, load_config
from scheduler.core.importer import (
    merge_teaching_and_rules, write_rules_yaml, write_teaching_yaml,
)

from . import sessions
from .schemas import (
    ConfigStatus, ImportConfirmRequest, ImportConfirmResponse, ImportPreview,
    PlanGetResponse, PlanPutRequest,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'

router = APIRouter(prefix='/api')


def _load_config_or_400():
    """`load_config` 在配置缺失/不自洽时抛 `ConfigError`——统一转成 400，
    不能让它裸传播成未格式化的 500。"""
    try:
        return load_config(DEFAULT_CONFIG_DIR)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@router.get('/config/status', response_model=ConfigStatus)
def config_status():
    teaching_path = DEFAULT_CONFIG_DIR / 'teaching.yaml'
    if not teaching_path.exists():
        return ConfigStatus(ready=False)
    import yaml
    data = yaml.safe_load(teaching_path.read_text(encoding='utf-8')) or {}
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
    import yaml

    cfg = _load_config_or_400()
    candidate = cfg.model_copy(deep=True)
    candidate.plans[body.grade] = body.plan
    try:
        candidate.validate_plan(body.grade)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    plans_path = DEFAULT_CONFIG_DIR / 'plans.yaml'
    raw = yaml.safe_load(plans_path.read_text(encoding='utf-8')) or {}
    raw.setdefault('plans', {})[body.grade] = body.plan
    plans_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                          encoding='utf-8')
    return PlanGetResponse(grade=body.grade, plan=body.plan,
                           reserved_slots=cfg.reserved_slots.get(body.grade, []))
