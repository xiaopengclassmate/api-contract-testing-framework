from __future__ import annotations

import allure
import pytest

from utils.contract import validate_schema
from utils.data_factory import expected_total, order_payload


@allure.feature("接口安全")
@allure.story("输入、鉴权与信息暴露")
@pytest.mark.security
class TestApiSecurity:
    @allure.title("批量赋值：客户端不能覆盖状态、金额与支付流水号")
    def test_mass_assignment_is_ignored(self, api_client, db_client):
        payload = order_payload()
        payload.update(
            {
                "status": "PAID",
                "total_amount": 0.01,
                "payment_reference": "hacked-reference",
                "is_deleted": True,
            }
        )

        body = api_client.create_order(payload).json()

        assert body["status"] == "PENDING"
        assert body["payment_reference"] is None
        assert body["total_amount"] == pytest.approx(expected_total(payload))
        row = db_client.order_row(body["id"])
        assert row is not None
        assert row["status"] == "PENDING"
        assert row["payment_reference"] is None
        assert row["is_deleted"] is False
        assert row["total_amount"] == pytest.approx(body["total_amount"])

    @allure.title("SQL 注入字符串被当作普通客户 ID，不发生数据泄露")
    def test_sql_injection_is_treated_as_data(self, api_client, db_client):
        malicious = "customer' OR '1'='1"
        created = api_client.create_order(
            order_payload(customer_id=malicious)
        ).json()

        assert created["customer_id"] == malicious
        listing = api_client.list_orders(customer_id=malicious).json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == created["id"]

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["customer_id"] == malicious

    @allure.title("畸形 Authorization 头统一返回 401")
    @pytest.mark.parametrize(
        "header",
        [
            "Basic YWRtaW46YWRtaW4=",
            "Bearer",
            "Bearer ",
            "Token abc.def.ghi",
            "Bearer not-a-jwt",
        ],
        ids=[
            "basic-auth",
            "bearer-without-token",
            "bearer-empty",
            "wrong-scheme",
            "invalid-jwt",
        ],
    )
    def test_malformed_authorization_is_rejected(
        self, anonymous_client, header
    ):
        response = anonymous_client.get(
            "/api/v1/orders",
            headers={"Authorization": header},
            expected_status=401,
        )
        validate_schema(response.json(), "error.json")

    @allure.title("错误响应不泄露堆栈、SQL、绝对路径或口令")
    def test_error_response_does_not_leak_internals(self, api_client):
        responses = [
            api_client.get_order("missing-order", expected_status=404),
            api_client.post(
                "/api/v1/orders",
                json={"customer_id": "", "items": []},
                expected_status=422,
            ),
        ]

        for response in responses:
            body = response.text.lower()
            for leaked in (
                "traceback",
                "sqlalchemy",
                "sqlite",
                "select ",
                "password",
                "site-packages",
                "c:\\",
            ):
                assert leaked not in body, (
                    f"错误响应泄露内部信息: {leaked}\n{response.text}"
                )
            validate_schema(response.json(), "error.json")

    @allure.title("响应包含基础安全头")
    @pytest.mark.parametrize("path", ["/health", "/openapi.json"])
    def test_security_headers_present(self, anonymous_client, path):
        response = anonymous_client.get(path, expected_status=200)

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert "geolocation=()" in response.headers["Permissions-Policy"]
        assert response.headers["Cache-Control"] == "no-store"

    @allure.title("非法 JSON 请求体返回 422 且服务不崩溃")
    def test_invalid_json_body_is_rejected(self, api_client):
        response = api_client.post(
            "/api/v1/orders",
            data="{not-json",
            headers={"Content-Type": "application/json"},
            expected_status=422,
        )
        validate_schema(response.json(), "error.json")

    @allure.title("软删除后的订单不能取消或支付")
    def test_deleted_order_is_not_operable(self, api_client):
        created = api_client.create_order(order_payload()).json()
        api_client.delete_order(created["id"])

        for action in (api_client.cancel_order, api_client.pay_order):
            response = action(created["id"], expected_status=404)
            validate_schema(response.json(), "error.json")
            assert response.json()["detail"] == "Order not found"

    @allure.title("OpenAPI 文档不泄露密钥与数据库配置")
    def test_openapi_does_not_leak_secrets(self, anonymous_client):
        text = anonymous_client.get(
            "/openapi.json", expected_status=200
        ).text.lower()

        for secret in ("jwt_secret", "database_url", "admin123"):
            assert secret not in text
