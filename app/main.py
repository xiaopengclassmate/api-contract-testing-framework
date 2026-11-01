from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import requests
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, schemas, settings
from app.database import get_db, init_db
from app.models import Order, OrderItem
from app.payment import PaymentGatewayError, charge


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Order API",
    version="1.0.0",
    description=(
        "用于接口自动化与契约测试演示的订单服务。"
        "支持 JWT 鉴权、订单 CRUD、支付网关调用与软删除。"
    ),
    lifespan=lifespan,
    openapi_tags=[
        {"name": "system", "description": "健康检查"},
        {"name": "auth", "description": "登录与令牌"},
        {"name": "orders", "description": "订单业务"},
    ],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """为所有响应补充基础安全头，避免 MIME 嗅探与点击劫持。"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=()"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _get_live_order(db: Session, order_id: str) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return order


@app.get("/health", tags=["system"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/auth/token",
    response_model=schemas.TokenResponse,
    tags=["auth"],
    summary="使用用户名密码获取 JWT",
)
def login(payload: schemas.TokenRequest) -> schemas.TokenResponse:
    if not auth.authenticate(payload.username, payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    return schemas.TokenResponse(
        access_token=auth.create_access_token(payload.username),
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )


@app.post(
    "/api/v1/orders",
    response_model=schemas.OrderOut,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
    summary="创建订单",
)
def create_order(
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> Order:
    total_amount = round(
        sum(item.unit_price * item.quantity for item in payload.items), 2
    )
    order = Order(
        id=str(uuid.uuid4()),
        customer_id=payload.customer_id,
        status="PENDING",
        total_amount=total_amount,
        currency=payload.currency,
    )
    order.items = [
        OrderItem(
            sku=item.sku,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=round(item.unit_price * item.quantity, 2),
        )
        for item in payload.items
    ]

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get(
    "/api/v1/orders/{order_id}",
    response_model=schemas.OrderOut,
    tags=["orders"],
    summary="查询订单详情",
)
def get_order(
    order_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> Order:
    return _get_live_order(db, order_id)


@app.get(
    "/api/v1/orders",
    response_model=schemas.OrderListOut,
    tags=["orders"],
    summary="分页查询订单",
)
def list_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    customer_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> dict:
    statement = select(Order).where(Order.is_deleted.is_(False))
    if status_filter:
        statement = statement.where(Order.status == status_filter)
    if customer_id:
        statement = statement.where(Order.customer_id == customer_id)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.order_by(Order.created_at.desc()).limit(limit).offset(offset)
    ).all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.post(
    "/api/v1/orders/{order_id}/cancel",
    response_model=schemas.OrderOut,
    tags=["orders"],
    summary="取消订单",
)
def cancel_order(
    order_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> Order:
    order = _get_live_order(db, order_id)

    if order.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paid orders cannot be cancelled",
        )
    if order.status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is already cancelled",
        )

    order.status = "CANCELLED"
    db.commit()
    db.refresh(order)
    return order


@app.post(
    "/api/v1/orders/{order_id}/pay",
    response_model=schemas.PaymentResult,
    tags=["orders"],
    summary="支付订单（调用外部支付网关）",
)
def pay_order(
    order_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> dict:
    order = _get_live_order(db, order_id)

    if order.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only pending orders can be paid",
        )

    try:
        reference = charge(order.id, order.total_amount, order.currency)
    except requests.Timeout:
        order.status = "FAILED"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Payment gateway timeout",
        )
    except PaymentGatewayError as exc:
        order.status = "FAILED"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Payment gateway error: {exc}",
        )

    order.status = "PAID"
    order.payment_reference = reference
    db.commit()
    db.refresh(order)
    return {"order": order, "payment_reference": reference}


@app.delete(
    "/api/v1/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["orders"],
    summary="软删除订单",
)
def delete_order(
    order_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(auth.get_current_user),
) -> Response:
    order = _get_live_order(db, order_id)

    if order.status == "PAID":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paid orders cannot be deleted",
        )

    order.is_deleted = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
