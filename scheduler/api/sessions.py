"""进程内存态：导入预览会话、求解任务。批次一是本地单用户工具，重启即清空。"""
import threading
import uuid
from typing import Dict, List, Optional


class ImportSession:
    def __init__(self, result, grade: str):
        self.result = result
        self.grade = grade


class SolveJob:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = 'pending'
        self.issues: List[dict] = []
        self.conflict: Optional[str] = None
        self.solutions: List = []
        self.violations: List[List] = []
        self.dataset = None
        self.cfg = None


_lock = threading.Lock()
_imports: Dict[str, ImportSession] = {}
_jobs: Dict[str, SolveJob] = {}


def save_import(result, grade: str) -> str:
    token = uuid.uuid4().hex
    with _lock:
        _imports[token] = ImportSession(result, grade)
    return token


def get_import(token: str) -> Optional[ImportSession]:
    with _lock:
        return _imports.get(token)


def create_job() -> SolveJob:
    job = SolveJob(uuid.uuid4().hex)
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> Optional[SolveJob]:
    with _lock:
        return _jobs.get(job_id)
