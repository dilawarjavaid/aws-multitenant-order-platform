import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "true",
    reason="Set RUN_DB_TESTS=true to run PostgreSQL integration tests",
)


@pytest.fixture
def payment_setup(monkeypatch):
    from app import order_service
    from app.database import engine
    from app.models import Product, Tenant
    from app.schemas import OrderCreate

    test_engine = create_engine(
        engine.url.set(database="order_platform_test")
    )

    try:
        with test_engine.connect() as connection:
            transaction = connection.begin()
            sessions = sessionmaker(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )

            try:
                monkeypatch.setattr(order_service, "SessionLocal", sessions)

                tenant_id = uuid4()
                product_id = uuid4()

                with sessions.begin() as session:
                    session.add(
                        Tenant(id=tenant_id, name="Payment Test Retailer")
                    )
                    session.flush()
                    session.add(
                        Product(
                            id=product_id,
                            tenant_id=tenant_id,
                            name="Payment Test Product",
                            currency="USD",
                            unit_price_minor=1999,
                            stock_quantity=10,
                        )
                    )

                order = order_service.create_order(
                    tenant_id,
                    OrderCreate(
                        items=[
                            {"product_id": product_id, "quantity": 2}
                        ]
                    ),
                )

                yield sessions, tenant_id, product_id, order.id
            finally:
                transaction.rollback()
    finally:
        test_engine.dispose()


def test_payment_confirms_order_once(payment_setup):
    from app.inventory import reserve_inventory
    from app.models import Order, Payment, Product
    from app.payments import confirm_order_payment

    sessions, tenant_id, product_id, order_id = payment_setup

    with sessions.begin() as session:
        reserve_inventory(session, tenant_id, order_id)
        payment = confirm_order_payment(session, tenant_id, order_id)

        payment_id = payment.id
        assert payment.status == "succeeded"
        assert payment.amount_minor == 3998
        assert payment.currency == "USD"

    # Retry payment in a separate transaction.
    with sessions.begin() as session:
        repeated = confirm_order_payment(session, tenant_id, order_id)
        assert repeated.id == payment_id

    with sessions() as session:
        order = session.get(Order, order_id)
        product = session.get(Product, product_id)
        payments = session.scalars(
            select(Payment).where(Payment.order_id == order_id)
        ).all()

        assert order is not None
        assert order.status == "confirmed"
        assert product is not None
        assert product.stock_quantity == 8
        assert len(payments) == 1
        assert payments[0].provider_reference == f"sim-{order_id}"

def test_payment_requires_inventory_reservation(payment_setup):
    from app.models import Order, Payment, Product
    from app.payment_simulator import PaymentValidationError
    from app.payments import confirm_order_payment

    sessions, tenant_id, product_id, order_id = payment_setup

    with pytest.raises(
        PaymentValidationError,
        match="Order inventory is not fully reserved",
    ):
        with sessions.begin() as session:
            confirm_order_payment(session, tenant_id, order_id)

    with sessions() as session:
        order = session.get(Order, order_id)
        product = session.get(Product, product_id)
        payments = session.scalars(
            select(Payment).where(Payment.order_id == order_id)
        ).all()

        assert order is not None
        assert order.status == "pending"
        assert product is not None
        assert product.stock_quantity == 10
        assert payments == []


def test_later_failure_rolls_back_payment_and_inventory(payment_setup):
    from app.inventory import reserve_inventory
    from app.models import InventoryReservation, Order, Payment, Product
    from app.payments import confirm_order_payment

    sessions, tenant_id, product_id, order_id = payment_setup

    with pytest.raises(RuntimeError, match="Simulated workflow failure"):
        with sessions.begin() as session:
            reserve_inventory(session, tenant_id, order_id)
            confirm_order_payment(session, tenant_id, order_id)
            raise RuntimeError("Simulated workflow failure")

    with sessions() as session:
        order = session.get(Order, order_id)
        product = session.get(Product, product_id)
        payments = session.scalars(
            select(Payment).where(Payment.order_id == order_id)
        ).all()
        reservations = session.scalars(
            select(InventoryReservation).where(
                InventoryReservation.order_id == order_id
            )
        ).all()

        assert order is not None
        assert order.status == "pending"
        assert product is not None
        assert product.stock_quantity == 10
        assert payments == []
        assert reservations == []