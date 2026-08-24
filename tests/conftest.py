"""全局测试隔离：session_store 的 SQLite 落在每个测试各自的临时目录，
不碰真实的 ~/.scheduler/scheduler.db，测试之间也不共享历史数据。"""
import pytest

from scheduler.core import session_store


@pytest.fixture(autouse=True)
def _isolated_session_db(tmp_path_factory, monkeypatch):
    # 用 tmp_path_factory 而不是 tmp_path——后者是测试函数自己也会拿去用的
    # 那份临时目录，一些测试会断言"这个目录下只有这几个文件"，跟这里落盘的
    # test_sessions.db 撞在一起就会假失败。这里单独要一块完全无关的临时目录。
    db_dir = tmp_path_factory.mktemp('session_store')
    monkeypatch.setattr(session_store, 'DB_PATH', db_dir / 'test_sessions.db')
