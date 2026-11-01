from __future__ import annotations

import allure
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from utils.contract import validate_schema
from utils.data_factory import unique_customer_id

MAX_EXAMPLES = 25


def _price() -> st.SearchStrategy[float]:
    """用“分”生成两位小数，避免随机浮点导致金额断言抖动。"""
    return st.integers(min_value=1, max_value=100_000).map(
        lambda cents: cents / 100
    )


def _line() -> st.SearchStrategy[dict]:
    return st.fixed_dictionaries(
        {
            "sku": st.uuids().map(str),
            "quantity": st.integers(min_value=1, max_value=100),
            "unit_price": _price(),
        }
    )


def _items(
    min_size: int = 1, max_size: int = 20
) -> st.SearchStrategy[list[dict]]:
    return st.lists(
        _line(),
        min_size=min_size,
        max_size=max_size,
        unique_by=lambda item: item["sku"],
    )


def _payload(items: list[dict]) -> dict:
    return {
        "customer_id": unique_customer_id("property"),
        "currency": "USD",
        "items": items,
    }


def _server_total(items: list[dict]) -> float:
    return round(
        sum(item["unit_price"] * item["quantity"] for item in items), 2
    )


SETTINGS = settings(
    max_examples=MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@allure.feature("属性测试")
@allure.story("订单金额与状态不变量")
@pytest.mark.property
class TestOrderProperties:
    @allure.title("任意合法订单：总价等于明细金额之和")
    @SETTINGS
    @given(items=_items())
    def test_total_matches_line_items(self, api_client, items):
        body = api_client.create_order(_payload(items)).json()
        validate_schema(body, "order.json")

        assert body["total_amount"] == pytest.approx(
            _server_total(items), abs=0.01
        )
        by_sku = {item["sku"]: item for item in body["items"]}
        assert len(by_sku) == len(items)
        for item in items:
            assert by_sku[item["sku"]]["subtotal"] == pytest.approx(
                round(item["unit_price"] * item["quantity"], 2), abs=0.01
            )

    @allure.title("商品行顺序不影响订单总价")
    @SETTINGS
    @given(items=_items(min_size=2, max_size=8))
    def test_item_order_does_not_change_total(self, api_client, items):
        first = api_client.create_order(_payload(items)).json()
        second = api_client.create_order(
            _payload(list(reversed(items)))
        ).json()

        assert first["total_amount"] == pytest.approx(
            second["total_amount"], abs=0.01
        )
        assert {item["sku"] for item in first["items"]} == {
            item["sku"] for item in second["items"]
        }

    @allure.title("取消是终态：重复取消冲突且数据库状态一致")
    @SETTINGS
    @given(items=_items())
    def test_cancel_is_terminal(self, api_client, db_client, items):
        created = api_client.create_order(_payload(items)).json()

        cancelled = api_client.cancel_order(created["id"]).json()
        assert cancelled["status"] == "CANCELLED"

        conflict = api_client.cancel_order(
            created["id"], expected_status=409
        )
        assert conflict.json()["detail"] == "Order is already cancelled"

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["status"] == "CANCELLED"

    @allure.title("软删除后订单不可见")
    @SETTINGS
    @given(items=_items())
    def test_soft_deleted_order_is_hidden(self, api_client, items):
        created = api_client.create_order(_payload(items)).json()
        api_client.delete_order(created["id"])

        missing = api_client.get_order(created["id"], expected_status=404)
        assert missing.json()["detail"] == "Order not found"

        listing = api_client.list_orders(
            customer_id=created["customer_id"]
        ).json()
        assert listing["total"] == 0
        assert created["id"] not in {
            item["id"] for item in listing["items"]
        }
