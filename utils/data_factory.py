from __future__ import annotations

import uuid


def unique_customer_id(prefix: str = "customer") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def order_payload(
    customer_id: str | None = None,
    items: list[dict] | None = None,
    currency: str = "USD",
) -> dict:
    return {
        "customer_id": customer_id or unique_customer_id(),
        "currency": currency,
        "items": items
        or [
            {"sku": "SKU-001", "quantity": 2, "unit_price": 19.99},
            {"sku": "SKU-002", "quantity": 1, "unit_price": 5.00},
        ],
    }


def expected_total(payload: dict) -> float:
    return round(
        sum(
            item["unit_price"] * item["quantity"]
            for item in payload["items"]
        ),
        2,
    )
