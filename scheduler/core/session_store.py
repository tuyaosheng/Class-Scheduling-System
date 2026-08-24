"""导入预览会话与求解任务的持久化：SQLite，重启不丢。

存到用户目录 `~/.scheduler/scheduler.db`（跟 settings_store.py 同一个文件、
不同表）——项目目录外，不进 git，打包成 PyInstaller 单 exe 后依然可用，
零额外依赖（Python 内置 sqlite3）。

这一层只管"按 id 存/取/列/删一段 JSON"，不认识 ImportSession/SolveJob/
Dataset 这些领域对象——那些类型属于 api 层（scheduler/api/sessions.py），
core 不能反向依赖 api。`data` 参数/返回值都是普通 dict，序列化/反序列化
成领域对象由调用方负责。
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path.home() / '.scheduler' / 'scheduler.db'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS import_sessions ('
                 'token TEXT PRIMARY KEY, grade TEXT NOT NULL, '
                 'created_at TEXT NOT NULL, data TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS solve_jobs ('
                 'job_id TEXT PRIMARY KEY, status TEXT NOT NULL, grade TEXT NOT NULL, '
                 'created_at TEXT NOT NULL, data TEXT NOT NULL)')
    return conn


# ---------------------------------------------------------------- 导入预览会话

def save_import(token: str, grade: str, data: dict) -> None:
    with _connect() as conn:
        conn.execute('INSERT OR REPLACE INTO import_sessions '
                     '(token, grade, created_at, data) VALUES (?, ?, ?, ?)',
                     (token, grade, _now(), json.dumps(data)))


def load_import(token: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute('SELECT data FROM import_sessions WHERE token = ?',
                           (token,)).fetchone()
    return json.loads(row[0]) if row else None


def list_imports() -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute('SELECT token, grade, created_at FROM import_sessions '
                            'ORDER BY created_at DESC').fetchall()
    return [{'token': r[0], 'grade': r[1], 'created_at': r[2]} for r in rows]


def delete_import(token: str) -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM import_sessions WHERE token = ?', (token,))


def clear_imports() -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM import_sessions')


# ---------------------------------------------------------------- 求解任务

def create_job(job_id: str, grade: str) -> None:
    """只在任务刚创建时调用一次——之后所有变化都走 update_job，
    这样 created_at 只在这里写一次，不会被后续多次落盘悄悄改掉。"""
    with _connect() as conn:
        conn.execute('INSERT INTO solve_jobs (job_id, status, grade, created_at, data) '
                     'VALUES (?, ?, ?, ?, ?)',
                     (job_id, 'pending', grade, _now(), json.dumps({})))


def update_job(job_id: str, status: str, data: dict) -> None:
    with _connect() as conn:
        conn.execute('UPDATE solve_jobs SET status = ?, data = ? WHERE job_id = ?',
                     (status, json.dumps(data), job_id))


def load_job(job_id: str) -> Optional[Dict]:
    with _connect() as conn:
        row = conn.execute('SELECT status, grade, created_at, data FROM solve_jobs '
                           'WHERE job_id = ?', (job_id,)).fetchone()
    if row is None:
        return None
    status, grade, created_at, data = row
    payload = json.loads(data)
    payload['status'] = status
    payload['grade'] = grade
    payload['created_at'] = created_at
    return payload


def list_jobs() -> List[Dict]:
    with _connect() as conn:
        rows = conn.execute('SELECT job_id, status, grade, created_at, data FROM solve_jobs '
                            'ORDER BY created_at DESC').fetchall()
    out = []
    for job_id, status, grade, created_at, data in rows:
        payload = json.loads(data)
        out.append({'job_id': job_id, 'status': status, 'grade': grade,
                    'created_at': created_at,
                    'candidate_count': len(payload.get('solutions', []))})
    return out


def delete_job(job_id: str) -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM solve_jobs WHERE job_id = ?', (job_id,))


def clear_jobs() -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM solve_jobs')
