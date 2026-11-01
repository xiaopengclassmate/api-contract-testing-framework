from __future__ import annotations

import time
from typing import Any

import allure
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

STATUS = int | tuple[int, ...] | list[int]


class ApiClient:
    """统一的 HTTP 客户端：鉴权、超时、重试、Allure 请求日志。"""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            backoff_factor=0.2,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def close(self) -> None:
        self.session.close()

    def clear_token(self) -> None:
        self.session.headers.pop("Authorization", None)

    def login(self, username: str, password: str) -> str:
        response = self.request(
            "POST",
            "/api/v1/auth/token",
            expected_status=200,
            json={"username": username, "password": password},
        )
        token = response.json()["access_token"]
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        return token

    def request(
        self,
        method: str,
        path: str,
        *,
        expected_status: STATUS | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        started = time.perf_counter()
        response = self.session.request(
            method, url, timeout=self.timeout, **kwargs
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        allure.attach(
            self._format_exchange(method, url, response, elapsed_ms),
            name="HTTP 请求/响应",
            attachment_type=allure.attachment_type.TEXT,
        )

        if expected_status is not None:
            expected = (
                expected_status
                if isinstance(expected_status, (tuple, list))
                else (expected_status,)
            )
            if response.status_code not in expected:
                raise AssertionError(
                    f"{method} {url} expected {expected}, "
                    f"got {response.status_code}: {response.text[:1000]}"
                )
        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", path, **kwargs)

    @allure.step("创建订单")
    def create_order(self, payload: dict) -> requests.Response:
        return self.post("/api/v1/orders", json=payload, expected_status=201)

    @allure.step("查询订单 {order_id}")
    def get_order(self, order_id: str, expected_status: STATUS = 200):
        return self.get(
            f"/api/v1/orders/{order_id}", expected_status=expected_status
        )

    @allure.step("查询订单列表")
    def list_orders(self, **params: Any) -> requests.Response:
        return self.get(
            "/api/v1/orders", params=params, expected_status=200
        )

    @allure.step("取消订单 {order_id}")
    def cancel_order(self, order_id: str, expected_status: STATUS = 200):
        return self.post(
            f"/api/v1/orders/{order_id}/cancel",
            expected_status=expected_status,
        )

    @allure.step("支付订单 {order_id}")
    def pay_order(self, order_id: str, expected_status: STATUS = 200):
        return self.post(
            f"/api/v1/orders/{order_id}/pay",
            expected_status=expected_status,
        )

    @allure.step("删除订单 {order_id}")
    def delete_order(self, order_id: str, expected_status: STATUS = 204):
        return self.delete(
            f"/api/v1/orders/{order_id}", expected_status=expected_status
        )

    @staticmethod
    def _format_exchange(
        method: str,
        url: str,
        response: requests.Response,
        elapsed_ms: float,
    ) -> str:
        body = response.text
        if len(body) > 4000:
            body = f"{body[:4000]}...<truncated>"
        return (
            f"{method} {url}\n"
            f"status: {response.status_code}\n"
            f"elapsed: {elapsed_ms:.0f} ms\n\n"
            f"{body}"
        )
