import os
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException

from app.schemas import OrderCreate, OrderResponse

app = FastAPI(
    title="Multi-Tenant Order Platform",
    description="An order management API for multiple retailers.",
    version="0.1.0",
)


@app.get("/health", tags=["Operations"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/orders", response_model=OrderResponse, status_code=201, tags=["Orders"])
def create_order_endpoint(
    request: OrderCreate,
    x_tenant_id: UUID = Header(),
) -> OrderResponse:
    if os.getenv("ENABLE_DEV_ORDER_API") != "true":
        raise HTTPException(status_code=404, detail="Not found")

    from app.order_service import TenantNotFoundError, create_order

    try:
        return create_order(x_tenant_id, request)
    except TenantNotFoundError:
        raise HTTPException(status_code=404, detail="Tenant not found") from None