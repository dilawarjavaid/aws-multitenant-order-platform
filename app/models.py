from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import UniqueConstraint

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_orders_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND quantity <= 1000",
            name="ck_order_items_quantity",
        ),
        CheckConstraint(
            "unit_price_minor IS NULL OR unit_price_minor >= 0",
            name="ck_order_items_price",
        ),
        CheckConstraint(
            "(unit_price_minor IS NULL AND currency IS NULL) OR "
            "(unit_price_minor IS NOT NULL AND currency IS NOT NULL)",
            name="ck_order_items_price_currency",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )
    aggregate_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    consumer_name: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )
    event_id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "unit_price_minor >= 0",
            name="ck_products_price",
        ),
        CheckConstraint(
            "stock_quantity >= 0",
            name="ck_products_stock",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class InventoryReservation(Base):
    __tablename__ = "inventory_reservations"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "product_id",
            name="uq_inventory_reservations_order_product",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_inventory_reservations_quantity",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )