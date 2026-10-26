"""隔离测试基座（archive redesign backend lane）。

严格要求：
- 在导入 backend 前设置 ARCHIVE_DEPLOY_DIR 指向临时隔离目录
- 必须使用真实 MySQL/MariaDB via Docker mysql:8.4 随机端口；禁止 SQLite 回退
- 通过真实 alembic upgrade 构建 schema，不用 metadata.create_all 假盖章
- 每个请求独立 Session 且挂到 request.state.archive_session，由 CommitRoute 提交
- 任何 setup 错误直接抛出，不吞掉
"""
from __future__ import annotations

import os
import atexit
import pathlib
import tempfile
import time
import uuid
import warnings
import random
import socket
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, inspect

# 必须在任何 backend 导入前设置隔离目录与口令
_TMP_DEPLOY = Path(tempfile.mkdtemp(prefix="archive-test-deploy-"))
os.environ.pop("ARCHIVE_CONFIG", None)
os.environ["ARCHIVE_DEPLOY_DIR"] = str(_TMP_DEPLOY)
os.environ["ARCHIVE_TOKEN"] = "test-token-123"
os.environ.setdefault("ARCHIVE_DB_NAME", "kinship_archive_test")
(_TMP_DEPLOY / "media").mkdir(parents=True, exist_ok=True)
(_TMP_DEPLOY / "config.toml").write_text('app_title="Test Archive"\n[database]\n', encoding="utf-8")

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

_DOCKER_CONTAINER: str | None = None
_TEST_DB_URL: str | None = None
def _cleanup_container():
    if _DOCKER_CONTAINER:
        subprocess.run(["docker", "rm", "-f", "-v", _DOCKER_CONTAINER], capture_output=True, timeout=20)
atexit.register(_cleanup_container)

def _launch_mysql_strict() -> str:
    global _DOCKER_CONTAINER, _TEST_DB_URL
    # 检查 docker 可用，严格失败不回退
    subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
    port = _free_port()
    container = f"archive-test-mysql-{uuid.uuid4().hex[:8]}"
    pwd = "testpw123"
    dbname = "kinship_archive_test"
    # 清理旧残留
    subprocess.run(["docker", "rm", "-f", container], capture_output=True, timeout=5)
    subprocess.run(
        [
            "docker", "run", "-d",
            "--name", container,
            "-e", f"MYSQL_ROOT_PASSWORD={pwd}",
            "-e", f"MYSQL_DATABASE={dbname}",
            "-p", f"127.0.0.1:{port}:3306",
            "mysql:8.4",
            "--character-set-server=utf8mb4",
            "--collation-server=utf8mb4_unicode_ci",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    _DOCKER_CONTAINER = container
    import pymysql  # type: ignore
    deadline = time.time() + 75
    last_err = None
    while time.time() < deadline:
        try:
            conn = pymysql.connect(host="127.0.0.1", port=port, user="root", password=pwd, database=dbname)
            conn.close()
            break
        except Exception as e:
            last_err = e
            time.sleep(1)
    else:
        raise RuntimeError(f"MySQL container {container} failed to become ready on port {port}: {last_err}")
    url = f"mysql+pymysql://root:{pwd}@127.0.0.1:{port}/{dbname}?charset=utf8mb4"
    os.environ["ARCHIVE_DB_HOST"] = "127.0.0.1"
    os.environ["ARCHIVE_DB_PORT"] = str(port)
    os.environ["ARCHIVE_DB_USER"] = "root"
    os.environ["ARCHIVE_DB_PASSWORD"] = pwd
    os.environ["ARCHIVE_DB_NAME"] = dbname
    _TEST_DB_URL = url
    return url

# 严格创建 MySQL；失败直接抛出，不回退 SQLite
_launch_mysql_strict()

# 此时再导入 backend，确保 settings 读取到正确的 DB；engine 指向真实 MySQL
from backend.config import settings  # noqa: E402
from backend.db import Base, engine as prod_engine, SessionLocal  # noqa: E402
import backend.models  # noqa: F401
from alembic.config import Config as AlembicConfig  # noqa: E402
from alembic import command as alembic_command  # noqa: E402

# 严格校验方言
assert "mysql" in prod_engine.url.drivername, f"测试必须使用 MySQL，当前 {prod_engine.url}"

# 使用真实 alembic 升级到 head（不使用 metadata.create_all 假表）
# alembic.ini 位于 backend/../../alembic.ini
_repo_root = Path(__file__).resolve().parents[1]
_alembic_ini = _repo_root / "alembic.ini"
assert _alembic_ini.is_file(), f"找不到 alembic.ini 在 {_alembic_ini}"
acfg = AlembicConfig(str(_alembic_ini))
acfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
# 确保不使用 prepend_sys_path 干扰
alembic_command.upgrade(acfg, "head")

# 校验最新 head
with prod_engine.connect() as conn:
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert rev == "a7c9d1e3b5f8", f"alembic_version 期望 a7c9d1e3b5f8，实际 {rev}"

# 验证 dialect 细节
inspector = inspect(prod_engine)
assert "idempotency_keys" in inspector.get_table_names()

# 提供给测试使用的 engine 即 prod_engine（同一隔离库）
_engine = prod_engine

@pytest.fixture(scope="session")
def db_engine():
    return _engine

@pytest.fixture(scope="session")
def deploy_dir():
    return _TMP_DEPLOY

@pytest.fixture
def db_session(db_engine):
    """保留给迁移测试直接操作 DB 的会话（不参与请求事务）。"""
    from sqlalchemy.orm import sessionmaker
    S = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False, future=True)
    s = S()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

@pytest.fixture
def client():
    """每个请求独立 Session，挂到 request.state.archive_session，CommitRoute 真正提交。默认 get_session 已实现该逻辑，无需覆盖。"""
    from fastapi.testclient import TestClient
    from backend.main import app
    c = TestClient(app)
    c.headers.update({"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]})
    yield c

@pytest.fixture
def person_factory(client):
    def _make(display_name=None, **kw):
        name = display_name or f"__t_{uuid.uuid4().hex[:6]}"
        payload = {"display_name": name, "relation_type": kw.pop("relation_type", "friend")}
        payload.update(kw)
        r = client.post("/api/persons", json=payload)
        assert r.status_code == 201, r.text
        return r.json()
    return _make

@pytest.fixture
def auth_headers():
    return {"X-Archive-Token": os.environ["ARCHIVE_TOKEN"]}

def pytest_sessionfinish(session, exitstatus):
    global _DOCKER_CONTAINER
    if _DOCKER_CONTAINER:
        try:
            subprocess.run(["docker", "rm", "-f", "-v", _DOCKER_CONTAINER], capture_output=True, timeout=10)
        except Exception:
            pass
    try:
        import shutil
        shutil.rmtree(str(_TMP_DEPLOY), ignore_errors=True)
    except Exception:
        pass
