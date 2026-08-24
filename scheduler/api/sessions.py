"""导入预览会话、求解任务：领域对象 <-> session_store 的 JSON dict 互转。

持久化在 SQLite（core/session_store.py），重启不丢；历史列表/删除/清空
也在这一层暴露，供 routes.py/ws.py 直接调用。
"""
import uuid
from typing import Dict, List, Optional

from scheduler.core import session_store
from scheduler.core.config import SchedulerConfig
from scheduler.core.importer import ImportResult
from scheduler.core.models import Dataset
from scheduler.core.rules import Rule
from scheduler.core.solver import Solution
from scheduler.core.verifier import Violation


class ImportSession:
    def __init__(self, result: ImportResult, grade: str, rule_engine: str = 'regex'):
        self.result = result
        self.grade = grade
        self.rule_engine = rule_engine


class SolveJob:
    def __init__(self, job_id: str, grade: str = ''):
        self.job_id = job_id
        self.grade = grade
        self.status = 'pending'
        self.issues: List[dict] = []
        self.conflict: Optional[str] = None
        self.solutions: List[Solution] = []
        self.violations: List[List[Violation]] = []
        self.dataset: Optional[Dataset] = None
        self.cfg: Optional[SchedulerConfig] = None
        self.rules: List[Rule] = []


def _job_to_data(job: SolveJob) -> dict:
    return {
        'issues': job.issues,
        'conflict': job.conflict,
        'solutions': [s.model_dump() for s in job.solutions],
        'violations': [[v.model_dump() for v in vs] for vs in job.violations],
        'dataset': job.dataset.model_dump() if job.dataset is not None else None,
        'cfg': job.cfg.model_dump() if job.cfg is not None else None,
        'rules': [r.model_dump() for r in job.rules],
    }


def _data_to_job(job_id: str, payload: dict) -> SolveJob:
    job = SolveJob(job_id, payload.get('grade', ''))
    job.status = payload.get('status', 'pending')
    job.issues = payload.get('issues', [])
    job.conflict = payload.get('conflict')
    job.solutions = [Solution(**s) for s in payload.get('solutions', [])]
    job.violations = [[Violation(**v) for v in vs] for vs in payload.get('violations', [])]
    job.dataset = Dataset(**payload['dataset']) if payload.get('dataset') else None
    job.cfg = SchedulerConfig(**payload['cfg']) if payload.get('cfg') else None
    job.rules = [Rule(**r) for r in payload.get('rules', [])]
    return job


# ---------------------------------------------------------------- 导入预览会话

def save_import(result: ImportResult, grade: str, rule_engine: str = 'regex') -> str:
    token = uuid.uuid4().hex
    payload = result.model_dump()
    payload['rule_engine'] = rule_engine
    session_store.save_import(token, grade, payload)
    return token


def get_import(token: str) -> Optional[ImportSession]:
    payload = session_store.load_import(token)
    if payload is None:
        return None
    rule_engine = payload.pop('rule_engine', 'regex')
    return ImportSession(ImportResult(**payload), grade=payload['dataset']['grade'],
                         rule_engine=rule_engine)


def list_imports() -> List[Dict]:
    return session_store.list_imports()


def delete_import(token: str) -> None:
    session_store.delete_import(token)


def clear_imports() -> None:
    session_store.clear_imports()


# ---------------------------------------------------------------- 求解任务

def create_job(grade: str = '') -> SolveJob:
    job = SolveJob(uuid.uuid4().hex, grade)
    session_store.create_job(job.job_id, grade)
    return job


def save_job(job: SolveJob) -> None:
    session_store.update_job(job.job_id, job.status, _job_to_data(job))


def get_job(job_id: str) -> Optional[SolveJob]:
    payload = session_store.load_job(job_id)
    if payload is None:
        return None
    return _data_to_job(job_id, payload)


def list_jobs() -> List[Dict]:
    return session_store.list_jobs()


def delete_job(job_id: str) -> None:
    session_store.delete_job(job_id)


def clear_jobs() -> None:
    session_store.clear_jobs()
