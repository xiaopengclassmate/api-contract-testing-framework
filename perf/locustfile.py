"""Locust 版本压测脚本（与 loadgen.py 同场景、同权重）。

环境允许安装依赖时使用：
    pip install locust
    python -m perf.run_perf            # 先起被测服务（或自行启动 uvicorn）
    locust -f perf/locustfile.py --host http://127.0.0.1:18000

无头模式（可直接进 CI）：
    locust -f perf/locustfile.py --host http://127.0.0.1:18000 \
        --headless -u 20 -r 5 -t 60s --only-summary
"""

from __future__ import annotations

import os
import random
import uuid

from locust import HttpUser, between, task

USERNAME = os.getenv("PERF_USERNAME", "admin")
PASSWORD = os.getenv("PERF_PASSWORD", "admin123")


class OrderUser(HttpUser):
    wait_time = between(0, 0.2)

    def on_start(self) -> None:
        self.customer_id = f"locust-{uuid.uuid4().hex[:8]}"
        self.order_ids: list[str] = []
        self.pending_ids: list[str] = []

        with self.client.post(
            "/api/v1/auth/token",
            json={"username": USERNAME, "password": PASSWORD},
            name="POST /auth/token",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed: HTTP {resp.status_code}")
                return
            self.client.headers["Authorization"] = (
                f"Bearer {resp.json()['access_token']}"
            )

    @task(50)
    def create_order(self) -> None:
        items = [
            {
                "sku": f"SKU-{random.randint(1000, 9999)}",
                "quantity": random.randint(1, 3),
                "unit_price": round(random.uniform(9.9, 999.0), 2),
            }
            for _ in range(random.randint(1, 3))
        ]
        with self.client.post(
            "/api/v1/orders",
            json={"customer_id": self.customer_id, "items": items},
            name="POST /orders",
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                order_id = resp.json()["id"]
                self.order_ids.append(order_id)
                self.pending_ids.append(order_id)
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:80]}")

    @task(20)
    def get_order(self) -> None:
        if not self.order_ids:
            return
        order_id = random.choice(self.order_ids)
        with self.client.get(
            f"/api/v1/orders/{order_id}",
            name="GET /orders/{id}",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")

    @task(15)
    def list_orders(self) -> None:
        with self.client.get(
            "/api/v1/orders",
            params={"customer_id": self.customer_id, "limit": 20},
            name="GET /orders",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")

    @task(10)
    def pay_order(self) -> None:
        if not self.pending_ids:
            return
        order_id = random.choice(self.pending_ids)
        with self.client.post(
            f"/api/v1/orders/{order_id}/pay",
            name="POST /orders/{id}/pay",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.pending_ids.remove(order_id)
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(5)
    def cancel_order(self) -> None:
        if not self.pending_ids:
            return
        order_id = random.choice(self.pending_ids)
        with self.client.post(
            f"/api/v1/orders/{order_id}/cancel",
            name="POST /orders/{id}/cancel",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.pending_ids.remove(order_id)
            else:
                resp.failure(f"HTTP {resp.status_code}")
