from __future__ import annotations

import allure
import pytest

from utils.contract import validate_schema
from utils.data_factory import unique_customer_id
from utils.data_loader import load_yaml

CASES = load_yaml("data/order_cases.yaml")


@allure.feature("订单接口")
@allure.story("参数校验")
@pytest.mark.regression
class TestOrderValidation:
    @allure.title("数据驱动：合法订单可以创建并正确计价")
    @pytest.mark.parametrize(
        "case",
        CASES["valid"],
        ids=[case["id"] for case in CASES["valid"]],
    )
    def test_valid_cases(self, api_client, case):
        payload = {
            "customer_id": unique_customer_id(case["customer_id"]),
            "currency": case["currency"],
            "items": case["items"],
        }
        response = api_client.post(
            "/api/v1/orders", json=payload, expected_status=201
        )

        body = response.json()
        validate_schema(body, "order.json")
        expected = round(
            sum(
                item["unit_price"] * item["quantity"]
                for item in case["items"]
            ),
            2,
        )
        assert body["total_amount"] == pytest.approx(expected)
        assert body["currency"] == case["currency"]

    @allure.title("数据驱动：非法订单返回 422 并指出字段")
    @pytest.mark.parametrize(
        "case",
        CASES["invalid"],
        ids=[case["id"] for case in CASES["invalid"]],
    )
    def test_invalid_cases(self, api_client, case):
        response = api_client.post(
            "/api/v1/orders", json=case["payload"], expected_status=422
        )

        body = response.json()
        validate_schema(body, "error.json")
        assert isinstance(body["detail"], list)
        locations = {
            str(part)
            for error in body["detail"]
            for part in error["loc"]
        }
        assert case["field"] in locations, (
            f"{case['description']} 未定位到字段 {case['field']}: {body}"
        )

    @allure.title("未登录不能创建订单")
    def test_create_requires_auth(self, anonymous_client):
        response = anonymous_client.post(
            "/api/v1/orders",
            json={
                "customer_id": "customer-001",
                "items": [
                    {"sku": "SKU-001", "quantity": 1, "unit_price": 9.9}
                ],
            },
            expected_status=401,
        )

        validate_schema(response.json(), "error.json")

    @allure.title("limit 超出范围返回 422")
    @pytest.mark.parametrize("limit", [0, 101], ids=["zero", "too-large"])
    def test_list_limit_validation(self, api_client, limit):
        response = api_client.get(
            "/api/v1/orders",
            params={"limit": limit},
            expected_status=422,
        )
        validate_schema(response.json(), "error.json")
