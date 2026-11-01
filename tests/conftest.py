from __future__ import annotations

import os
import platform
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

# 必须在导入 app 之前覆盖配置，保证测试使用独立数据库与假网关。
_TMP_DIR = Path(tempfile.mkdtemp(prefix="order-api-tests-"))
os.environ["DATABASE_URL"] = (
    f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
)
os.environ["PAYMENT_GATEWAY_URL"] = "https://payments.test/charge"
os.environ["PAYMENT_TIMEOUT_SECONDS"] = "2"
os.environ["JWT_SECRET"] = "test-secret-for-api-contract-tests-32b"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123"

from app import settings  # noqa: E402
from utils.api_client import ApiClient  # noqa: E402
from utils.db_client import DbClient  # noqa: E402


def pytest_sessionfinish(session, exitstatus) -> None:
    """把运行环境写入 Allure 报告，便于追溯。"""
    results_dir = Path("allure-results")
    if not results_dir.exists():
        return
    lines = [
        f"Python={platform.python_version()}",
        f"Platform={platform.platform()}",
        "Test.Framework=pytest + allure-pytest",
        "Database=SQLite (per-process temporary)",
        "Payment.Gateway=responses mock",
        f"Admin.User={settings.ADMIN_USERNAME}",
    ]
    results_dir.joinpath("environment.properties").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout: float = 20.0) -> None:
    import requests

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/health", timeout=0.5)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"API server did not become healthy: {last_error}")


@pytest.fixture(scope="session")
def api_server() -> str:
    """在后台线程启动真实 uvicorn，测试通过 HTTP 访问。"""
    import uvicorn

    from app.database import init_db
    from app.main import app

    init_db()
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_for_health(base_url)

    yield base_url

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def api_client(api_server: str):
    client = ApiClient(api_server)
    client.login(settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
    yield client
    client.close()


@pytest.fixture
def anonymous_client(api_server: str):
    client = ApiClient(api_server)
    yield client
    client.close()


@pytest.fixture(scope="session")
def db_client():
    from app.database import init_db

    # 只跑契约/校验类用例时不会启动服务，这里确保表结构存在。
    init_db()
    client = DbClient(os.environ["DATABASE_URL"])
    yield client
    client.dispose()


@pytest.fixture(autouse=True)
def clean_database(db_client):
    """每个用例结束后清库，避免订单数据相互污染。"""
    yield
    db_client.clear()
