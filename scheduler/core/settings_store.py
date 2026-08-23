"""本地设置持久化：SQLite 键值存储。

存到用户目录 `~/.scheduler/scheduler.db`——项目目录外,不进 git,打包成
PyInstaller 单 exe 后依然可用。零额外依赖(Python 内置 sqlite3)。

被两处共用：
  - scheduler/ai/rule_parser.py 读 key（AI 规则解析）
  - scheduler/api/routes.py 读写（/api/settings/ai 端点）

「本地设置 → 环境变量」的回退顺序只在这里实现一处(get_ai_api_key),
两端点都走它,避免各自推导悄悄分叉。key 明文存储——本地单用户工具,
与 gh/git 等 CLI 同款做法,不引入加密依赖。
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / '.scheduler' / 'scheduler.db'


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS settings '
                 '(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return conn


def get_setting(key: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                     (key, value))


def delete_setting(key: str) -> None:
    with _connect() as conn:
        conn.execute('DELETE FROM settings WHERE key = ?', (key,))


def get_ai_api_key() -> Optional[str]:
    """AI key 的唯一事实来源：本地设置优先,回退环境变量。"""
    local = get_setting('ai.api_key')
    return local if local else os.environ.get('ANTHROPIC_API_KEY')
