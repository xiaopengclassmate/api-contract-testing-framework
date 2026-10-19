from __future__ import annotations

import json
import re

import allure
import pytest
import requests as requests_lib
import responses

from app import settings
from utils.contract import validate_schema
from utils.data_factory import order_payload

# responses 会拦截进程内所有 requests 调用，本地服务需要放行。
LOCAL_PASSTHRU = re.compile(r"^http://127\.0\.0\.1:\d+")


@allure.feature("外部依赖 Mock")
@allure.story("支付网关")
@pytest.mark.mock
class TestPaymentGateway:
    @staticmethod
    def _create_order(api_client) -> dict:
        return api_client.create_order(order_payload()).json()

    @allure.title("网关成功：订单变为 PAID 并保存支付流水号")
    @responses.activate
    def test_payment_success(self, api_client, db_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            json={"reference": "pay_TEST-0001", "status": "succeeded"},
            status=200,
        )

        response = api_client.pay_order(order["id"])
        body = response.json()

        validate_schema(body, "payment_result.json")
        assert body["order"]["status"] == "PAID"
        assert body["order"]["payment_reference"] == "pay_TEST-0001"
        assert body["payment_reference"] == "pay_TEST-0001"

        assert len(responses.calls) == 1
        sent = json.loads(responses.calls[0].request.body)
        assert sent == {
            "order_id": order["id"],
            "amount": order["total_amount"],
            "currency": order["currency"],
        }

        row = db_client.order_row(order["id"])
        assert row["status"] == "PAID"
        assert row["payment_reference"] == "pay_TEST-0001"

    @allure.title("网关 500：返回 502，订单标记为 FAILED")
    @responses.activate
    def test_payment_gateway_error(self, api_client, db_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            json={"error": "gateway down"},
            status=500,
        )

        response = api_client.pay_order(order["id"], expected_status=502)

        validate_schema(response.json(), "error.json")
        assert "Payment gateway error" in response.json()["detail"]
        assert db_client.order_row(order["id"])["status"] == "FAILED"

    @allure.title("网关超时：返回 504，订单标记为 FAILED")
    @responses.activate
    def test_payment_gateway_timeout(self, api_client, db_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            body=requests_lib.exceptions.Timeout("gateway timeout"),
        )

        response = api_client.pay_order(order["id"], expected_status=504)

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Payment gateway timeout"
        assert db_client.order_row(order["id"])["status"] == "FAILED"

    @allure.title("网关返回非 JSON：返回 502，订单标记为 FAILED")
    @responses.activate
    def test_payment_gateway_non_json(self, api_client, db_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            body="<html>bad gateway</html>",
            status=200,
            content_type="text/html",
        )

        response = api_client.pay_order(order["id"], expected_status=502)

        assert "non-JSON" in response.json()["detail"]
        assert db_client.order_row(order["id"])["status"] == "FAILED"

    @allure.title("网关未返回流水号：返回 502，订单标记为 FAILED")
    @responses.activate
    def test_payment_gateway_missing_reference(
        self, api_client, db_client
    ):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            json={"status": "succeeded"},
            status=200,
        )

        response = api_client.pay_order(order["id"], expected_status=502)

        assert "no payment reference" in response.json()["detail"]
        assert db_client.order_row(order["id"])["status"] == "FAILED"

    @allure.title("已支付订单再次支付返回 409，且不会重复调用网关")
    @responses.activate
    def test_pay_twice_conflict(self, api_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            json={"reference": "pay_TEST-0002"},
            status=200,
        )
        api_client.pay_order(order["id"])

        response = api_client.pay_order(order["id"], expected_status=409)

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Only pending orders can be paid"
        assert len(responses.calls) == 1

    @allure.title("已支付订单不能取消或删除")
    @responses.activate
    def test_paid_order_is_immutable(self, api_client):
        responses.add_passthru(LOCAL_PASSTHRU)
        order = self._create_order(api_client)
        responses.add(
            responses.POST,
            settings.PAYMENT_GATEWAY_URL,
            json={"reference": "pay_TEST-0003"},
            status=200,
        )
        api_client.pay_order(order["id"])

        cancel = api_client.cancel_order(order["id"], expected_status=409)
        delete = api_client.delete_order(order["id"], expected_status=409)

        assert cancel.json()["detail"] == "Paid orders cannot be cancelled"
        assert delete.json()["detail"] == "Paid orders cannot be deleted"

    @allure.title("已取消订单不能支付")
    def test_pay_cancelled_order(self, api_client):
        order = self._create_order(api_client)
        api_client.cancel_order(order["id"])

        response = api_client.pay_order(order["id"], expected_status=409)

        validate_schema(response.json(), "error.json")
        assert response.json()["detail"] == "Only pending orders can be paid"

    @allure.title("支付不存在的订单返回 404")
    def test_pay_unknown_order(self, api_client):
        response = api_client.pay_order(
            "00000000-0000-0000-0000-000000000000", expected_status=404
        )
        assert response.json()["detail"] == "Order not found"
