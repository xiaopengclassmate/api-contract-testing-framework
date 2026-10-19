from __future__ import annotations

import allure
import pytest
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

from utils.contract import SCHEMA_DIR, load_schema, validate_schema
from utils.data_factory import order_payload

CONTRACT_FILES = [
    "order.json",
    "order_list.json",
    "error.json",
    "token.json",
    "payment_result.json",
    "post.json",
]

REQUIRED_PATHS = {
    "/health",
    "/api/v1/auth/token",
    "/api/v1/orders",
    "/api/v1/orders/{order_id}",
    "/api/v1/orders/{order_id}/cancel",
    "/api/v1/orders/{order_id}/pay",
}


@allure.feature("契约测试")
@allure.story("消费者驱动契约")
@pytest.mark.contract
class TestContracts:
    @allure.title("所有 JSON Schema 文件本身合法")
    @pytest.mark.parametrize("schema_name", CONTRACT_FILES)
    def test_schema_files_are_valid(self, schema_name):
        Draft202012Validator.check_schema(load_schema(schema_name))

    @allure.title("OpenAPI 文档符合 OpenAPI 规范")
    def test_openapi_spec_is_valid(self, api_client):
        response = api_client.get("/openapi.json", expected_status=200)
        spec = response.json()

        validate(spec)
        assert spec["info"]["title"] == "Order API"
        assert spec["openapi"].startswith("3.")

    @allure.title("OpenAPI 文档覆盖全部对外路径")
    def test_openapi_declares_expected_paths(self, api_client):
        spec = api_client.get("/openapi.json", expected_status=200).json()
        assert REQUIRED_PATHS.issubset(set(spec["paths"]))

    @allure.title("服务端 OrderOut 字段与消费者契约一致")
    def test_provider_schema_matches_consumer_contract(self, api_client):
        spec = api_client.get("/openapi.json", expected_status=200).json()
        provider = spec["components"]["schemas"]["OrderOut"]
        consumer = load_schema("order.json")

        assert set(provider["required"]) == set(consumer["required"])
        assert set(provider["properties"]) == set(
            consumer["properties"]
        )

    @allure.title("创建订单响应满足 Order 契约")
    def test_create_order_contract(self, api_client):
        response = api_client.create_order(order_payload())
        validate_schema(response.json(), "order.json")

    @allure.title("订单列表响应满足 OrderList 契约")
    def test_order_list_contract(self, api_client):
        api_client.create_order(order_payload())
        response = api_client.list_orders()
        validate_schema(response.json(), "order_list.json")

    @allure.title("错误响应满足 ErrorResponse 契约")
    def test_error_contract(self, api_client):
        response = api_client.get_order(
            "00000000-0000-0000-0000-000000000000", expected_status=404
        )
        validate_schema(response.json(), "error.json")

    @allure.title("登录响应满足 Token 契约")
    def test_token_contract(self, anonymous_client):
        from app import settings

        response = anonymous_client.post(
            "/api/v1/auth/token",
            json={
                "username": settings.ADMIN_USERNAME,
                "password": settings.ADMIN_PASSWORD,
            },
            expected_status=200,
        )
        validate_schema(response.json(), "token.json")

    @allure.title("契约校验能发现破坏性变更（缺少必填字段）")
    def test_contract_detects_breaking_change(self):
        broken = {
            "id": "order-1",
            "customer_id": "customer-1",
            "status": "PENDING",
            # 缺少 total_amount / items 等必填字段
        }
        with pytest.raises(AssertionError, match="契约校验失败"):
            validate_schema(broken, "order.json")

    @allure.title("契约校验能发现多出的非契约字段")
    def test_contract_rejects_unexpected_field(self, api_client):
        body = api_client.create_order(order_payload()).json()
        body["unexpected_field"] = "not-in-contract"

        with pytest.raises(AssertionError, match="契约校验失败"):
            validate_schema(body, "order.json")

    @allure.title("契约目录包含预期的 Schema 文件")
    def test_schema_directory(self):
        names = {path.name for path in SCHEMA_DIR.glob("*.json")}
        assert set(CONTRACT_FILES).issubset(names)
