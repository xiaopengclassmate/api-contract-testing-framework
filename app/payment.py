import requests

from app import settings


class PaymentGatewayError(Exception):
    """支付网关返回异常时抛出。"""


def charge(order_id: str, amount: float, currency: str) -> str:
    """调用外部支付网关，返回支付流水号。"""
    response = requests.post(
        settings.PAYMENT_GATEWAY_URL,
        json={
            "order_id": order_id,
            "amount": round(amount, 2),
            "currency": currency,
        },
        timeout=settings.PAYMENT_TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        raise PaymentGatewayError(
            f"gateway returned HTTP {response.status_code}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise PaymentGatewayError("gateway returned non-JSON response") from exc

    reference = data.get("reference")
    if not reference:
        raise PaymentGatewayError("gateway returned no payment reference")
    return str(reference)
