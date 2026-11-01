from __future__ import annotations

import allure
import pytest

from utils.data_factory import order_payload


@allure.feature("数据库校验")
@allure.story("订单持久化")
@pytest.mark.db
class TestOrderPersistence:
    @allure.title("创建订单后主表与明细表都正确落库")
    def test_create_persists_order_and_items(self, api_client, db_client):
        payload = order_payload()
        created = api_client.create_order(payload).json()

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["customer_id"] == payload["customer_id"]
        assert row["status"] == "PENDING"
        assert row["currency"] == payload["currency"]
        assert row["total_amount"] == pytest.approx(
            created["total_amount"]
        )
        assert row["payment_reference"] is None
        assert row["is_deleted"] is False
        assert row["created_at"]
        assert row["updated_at"]

        items = db_client.items_for(created["id"])
        assert len(items) == len(payload["items"])
        assert [item["sku"] for item in items] == sorted(
            item["sku"] for item in payload["items"]
        )
        for item in items:
            assert item["subtotal"] == pytest.approx(
                round(item["quantity"] * item["unit_price"], 2)
            )

    @allure.title("取消订单只更新状态，不删除数据")
    def test_cancel_updates_status_in_db(self, api_client, db_client):
        created = api_client.create_order(order_payload()).json()

        api_client.cancel_order(created["id"])

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["status"] == "CANCELLED"
        assert row["is_deleted"] is False
        assert len(db_client.items_for(created["id"])) == 2

    @allure.title("删除订单是软删除：保留记录并标记 is_deleted")
    def test_delete_is_soft_delete(self, api_client, db_client):
        created = api_client.create_order(order_payload()).json()
        before = db_client.order_count()

        api_client.delete_order(created["id"])

        row = db_client.order_row(created["id"])
        assert row is not None
        assert row["is_deleted"] is True
        assert row["status"] == "PENDING"
        assert db_client.order_count() == before

    @allure.title("多笔订单会写入多条独立记录")
    def test_multiple_orders_are_persisted(self, api_client, db_client):
        ids = {
            api_client.create_order(order_payload()).json()["id"]
            for _ in range(3)
        }

        assert db_client.order_count() == 3
        assert all(db_client.order_row(order_id) for order_id in ids)
