from pydantic import BaseModel, ConfigDict, Field


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class OrderItemIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=100)
    unit_price: float = Field(gt=0, le=1_000_000)


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=64)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    quantity: int
    unit_price: float
    subtotal: float


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    status: str
    total_amount: float
    currency: str
    payment_reference: str | None
    created_at: str
    updated_at: str
    items: list[OrderItemOut]


class OrderListOut(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int


class PaymentResult(BaseModel):
    order: OrderOut
    payment_reference: str


class ErrorResponse(BaseModel):
    detail: str
