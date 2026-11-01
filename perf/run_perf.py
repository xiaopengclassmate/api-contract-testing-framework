"""一键跑压测：起网关替身 → 起被测服务 → 跑场景 → 出报告。

用法（在项目根目录）：
    python -m perf.run_perf --profile baseline
    python -m perf.run_perf --profile load --users 20 --duration 60
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import requests  # noqa: E402

from perf import fake_gateway, loadgen  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{base_url}/health", timeout=0.5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    raise RuntimeError("被测服务未在预期时间内启动")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="订单服务性能测试编排器")
    parser.add_argument("--profile", choices=sorted(loadgen.PROFILES), default="baseline")
    parser.add_argument("--users", type=int)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--spawn-rate", type=float)
    parser.add_argument("--think-time", type=float)
    parser.add_argument("--gateway-delay-ms", type=int, default=0)
    parser.add_argument("--keep-db", action="store_true", help="保留本次压测数据库")
    args = parser.parse_args(argv)

    # 必须在导入 app 之前设置环境变量
    stamp = time.strftime("%Y%m%d-%H%M%S")
    data_dir = BASE_DIR / "perf" / ".data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / f"perf-{stamp}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["JWT_SECRET"] = "perf-secret-key-for-local-load-tests"
    os.environ["ADMIN_USERNAME"] = "admin"
    os.environ["ADMIN_PASSWORD"] = "admin123"
    os.environ["PAYMENT_TIMEOUT_SECONDS"] = "2"

    gateway_port = _free_port()
    api_port = _free_port()
    os.environ["PAYMENT_GATEWAY_URL"] = f"http://127.0.0.1:{gateway_port}/charge"

    gateway = fake_gateway.serve(gateway_port, delay_ms=args.gateway_delay_ms)

    import uvicorn

    from app.database import init_db
    from app.main import app

    init_db()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=api_port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{api_port}"
    _wait_health(base_url)

    profile = loadgen.PROFILES[args.profile]
    cfg = loadgen.Config(
        base_url=base_url,
        profile=args.profile,
        users=args.users or profile["users"],
        duration=args.duration or profile["duration"],
        spawn_rate=args.spawn_rate or profile["spawn_rate"],
        think_time=(
            args.think_time
            if args.think_time is not None
            else profile["think_time"]
        ),
    )

    try:
        summary = loadgen.run(cfg)
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        gateway.shutdown()
        if not args.keep_db:
            from app.database import engine

            engine.dispose()  # Windows 下不释放连接会删不掉库文件
            try:
                db_path.unlink(missing_ok=True)
            except PermissionError:
                print(f"[run_perf] 数据库文件被占用，已保留：{db_path}")

    return 0 if all(check["pass"] for check in summary["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
