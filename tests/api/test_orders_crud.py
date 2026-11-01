from __future__ import annotations

import allure
import pytest

from utils.contract import validate_schema
from utils.data_factory import expected_total, order_payload, unique_customer_id


@allure.feature("订单接口")
@allure.story("订单生命周期")
@pytest.mark.smoke
class TestOrdersCrud:
    @allure.title("创建订单：状态、金额与明细正确")
    def test_create_order(self, api_client):
        payload = order_payload()
        response = api_client.post(
            "/api/v1/orders", json=payload, expected_status=201
        )

        body = response.json()
        validate_schema(body, "order.json")
        assert body["status"] == "PENDING"
        assert body["customer_id"] == payload["customer_id"]
        assert body["currency"] == payload["currency"]
        assert body["total_amount"] == pytest.approx(
            expected_total(payload)
        )
        assert body["payment_reference"] is None
        assert len(body["items"]) == len(payload["items"])
        assert body["created_at"]
        assert body["updated_at"]

    @allure.title("按 ID 查询订单")
    def test_get_order_by_id(self, api_client):
        created = api_client.create_order(order_payload()).json()

        response = api_client.get_order(created["id"])
        body = response.json()

        validate_schema(body, "order.json")
        assert body["id"] == created["id"]
        assert body["total_amount"] == created["total_amount"]

    @allure.title("查询不存在的订单返回 404")
    def test_get_unknown_order(self, api_client):
        response = api_client.get_order(
            "00000000-0000-0000-0000-000000000000", expected_status=404
        )

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Order not found"

    @allure.title("列表支持按客户与状态过滤")
    def test_list_orders_with_filters(self, api_client):
        customer_id = unique_customer_id()
        first = api_client.create_order(
            order_payload(customer_id=customer_id)
        ).json()
        second = api_client.create_order(
            order_payload(customer_id=customer_id)
        ).json()
        other = api_client.create_order(order_payload()).json()

        by_customer = api_client.list_orders(
            customer_id=customer_id
        ).json()
        validate_schema(by_customer, "order_list.json")
        assert by_customer["total"] == 2
        assert {item["id"] for item in by_customer["items"]} == {
            first["id"],
            second["id"],
        }

        api_client.cancel_order(first["id"])
        cancelled = api_client.list_orders(
            customer_id=customer_id, status="CANCELLED"
        ).json()
        assert cancelled["total"] == 1
        assert cancelled["items"][0]["id"] == first["id"]

        all_orders = api_client.list_orders().json()
        ids = {item["id"] for item in all_orders["items"]}
        assert other["id"] in ids

    @allure.title("列表分页返回正确的 limit/offset/total")
    def test_list_orders_pagination(self, api_client):
        for _ in range(3):
            api_client.create_order(order_payload())

        first_page = api_client.list_orders(limit=2, offset=0).json()
        second_page = api_client.list_orders(limit=2, offset=2).json()

        validate_schema(first_page, "order_list.json")
        validate_schema(second_page, "order_list.json")
        assert first_page["total"] == 3
        assert first_page["limit"] == 2
        assert first_page["offset"] == 0
        assert len(first_page["items"]) == 2
        assert len(second_page["items"]) == 1
        assert {
            item["id"] for item in first_page["items"]
        }.isdisjoint({item["id"] for item in second_page["items"]})

    @allure.title("offset 超出总数时返回空列表但 total 正确")
    def test_list_offset_beyond_total(self, api_client):
        for _ in range(2):
            api_client.create_order(order_payload())

        page = api_client.list_orders(offset=100).json()

        assert page["total"] == 2
        assert page["items"] == []
        assert page["offset"] == 100

    @allure.title("limit 边界值 1 和 100 可用")
    @pytest.mark.parametrize("limit", [1, 100], ids=["min", "max"])
    def test_list_limit_boundaries(self, api_client, limit):
        for _ in range(3):
            api_client.create_order(order_payload())

        page = api_client.list_orders(limit=limit).json()

        assert page["limit"] == limit
        assert page["total"] == 3
        assert len(page["items"]) == min(limit, 3)

    @allure.title("Unicode 客户 ID 与 SKU 可以正确保存和查询")
    def test_unicode_customer_and_sku(self, api_client, db_client):
        customer_id = "客户-咖啡-001"
        payload = order_payload(
            customer_id=customer_id,
            items=[
                {
                    "sku": "商品-拿铁-☕",
                    "quantity": 2,
                    "unit_price": 18.50,
                }
            ],
        )

        created = api_client.create_order(payload).json()

        assert created["customer_id"] == customer_id
        assert created["items"][0]["sku"] == "商品-拿铁-☕"
        assert created["total_amount"] == pytest.approx(37.00)

        listing = api_client.list_orders(customer_id=customer_id).json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == created["id"]

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["customer_id"] == customer_id
        assert db_client.items_for(created["id"])[0]["sku"] == "商品-拿铁-☕"

    @allure.title("重复 SKU 按两条明细保留并分别计价")
    def test_duplicate_skus_are_not_deduplicated(self, api_client):
        payload = order_payload(
            items=[
                {"sku": "SKU-DUP", "quantity": 1, "unit_price": 10.00},
                {"sku": "SKU-DUP", "quantity": 3, "unit_price": 10.00},
            ]
        )

        created = api_client.create_order(payload).json()

        assert len(created["items"]) == 2
        assert created["total_amount"] == pytest.approx(40.00)
        assert sum(
            item["subtotal"] for item in created["items"]
        ) == pytest.approx(40.00)

    @allure.title("金额按两位小数四舍五入")
    def test_amount_rounds_to_two_decimals(self, api_client):
        payload = order_payload(
            items=[
                {"sku": "SKU-ROUND", "quantity": 3, "unit_price": 0.10}
            ]
        )

        created = api_client.create_order(payload).json()

        assert created["total_amount"] == pytest.approx(0.30)
        assert created["items"][0]["subtotal"] == pytest.approx(0.30)

    @allure.title("重复删除已软删除订单返回 404")
    def test_delete_twice_returns_404(self, api_client):
        created = api_client.create_order(order_payload()).json()
        api_client.delete_order(created["id"])

        response = api_client.delete_order(
            created["id"], expected_status=404
        )

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Order not found"

    @allure.title("取消订单后状态变为 CANCELLED")
    def test_cancel_order(self, api_client):
        created = api_client.create_order(order_payload()).json()

        response = api_client.cancel_order(created["id"])
        body = response.json()

        validate_schema(body, "order.json")
        assert body["status"] == "CANCELLED"

    @allure.title("重复取消订单返回 409")
    def test_cancel_twice_conflict(self, api_client):
        created = api_client.create_order(order_payload()).json()
        api_client.cancel_order(created["id"])

        response = api_client.cancel_order(
            created["id"], expected_status=409
        )

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Order is already cancelled"

    @allure.title("软删除订单后详情 404 且列表不可见")
    def test_soft_delete_order(self, api_client):
        created = api_client.create_order(order_payload()).json()

        api_client.delete_order(created["id"])

        api_client.get_order(created["id"], expected_status=404)
        listing = api_client.list_orders().json()
        assert created["id"] not in {
            item["id"] for item in listing["items"]
        }

    @allure.title("删除不存在的订单返回 404")
    def test_delete_unknown_order(self, api_client):
        response = api_client.delete_order(
            "00000000-0000-0000-0000-000000000000", expected_status=404
        )
        validate_schema(response.json(), "error.json")
