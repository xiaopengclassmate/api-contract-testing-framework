from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from app.models import Order, OrderItem


class DbClient:
    """直连测试数据库做断言，验证 API 行为是否真正落库。"""

    def __init__(self, db_url: str) -> None:
        connect_args = (
            {"check_same_thread": False} if db_url.startswith("sqlite") else {}
        )
        self.engine = create_engine(db_url, connect_args=connect_args)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def dispose(self) -> None:
        self.engine.dispose()

    def order_row(self, order_id: str) -> dict[str, Any] | None:
        with self.Session() as session:
            order = session.get(Order, order_id)
            if order is None:
                return None
            return {
                "id": order.id,
                "customer_id": order.customer_id,
                "status": order.status,
                "total_amount": order.total_amount,
                "currency": order.currency,
                "payment_reference": order.payment_reference,
                "is_deleted": order.is_deleted,
                "created_at": order.created_at,
                "updated_at": order.updated_at,
            }

    def items_for(self, order_id: str) -> list[dict[str, Any]]:
        with self.Session() as session:
            items = session.scalars(
                select(OrderItem)
                .where(OrderItem.order_id == order_id)
                .order_by(OrderItem.id)
            ).all()
            return [
                {
                    "sku": item.sku,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "subtotal": item.subtotal,
                }
                for item in items
            ]

    def order_count(self) -> int:
        with self.Session() as session:
            return session.scalar(select(func.count()).select_from(Order)) or 0

    def clear(self) -> None:
        """清理测试数据，保证用例之间互不影响。"""
        with self.Session() as session:
            session.execute(delete(OrderItem))
            session.execute(delete(Order))
            session.commit()
