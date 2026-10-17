from uuid import uuid4

import pytest

from app.payment_simulator import (
    PaymentValidationError,
    calculate_payment_amount,
    simulate_payment,
)
from app.schemas import OrderItemResponse


def make_item(quantity=2, price=1999, currency="USD"):
    return OrderItemResponse(
        id=uuid4(),
        product_id=uuid4(),
        quantity=quantity,
        unit_price_minor=price,
        currency=currency,
    )


def test_calculates_amount_from_saved_prices():
    items = [
        make_item(quantity=2, price=1999),
        make_item(quantity=1, price=500),
    ]

    assert calculate_payment_amount(items) == (4498, "USD")


def test_rejects_empty_order():
    with pytest.raises(PaymentValidationError, match="Order has no items"):
        calculate_payment_amount([])


def test_rejects_missing_saved_price():
    with pytest.raises(
        PaymentValidationError,
        match="Order item has no saved price",
    ):
        calculate_payment_amount([make_item(price=None, currency=None)])


def test_rejects_mixed_currencies():
    with pytest.raises(
        PaymentValidationError,
        match="Order contains multiple currencies",
    ):
        calculate_payment_amount(
            [
                make_item(currency="USD"),
                make_item(currency="EUR"),
            ]
        )


def test_rejects_unsupported_currency():
    with pytest.raises(
        PaymentValidationError,
        match="Simulator supports USD only",
    ):
        calculate_payment_amount([make_item(currency="EUR")])


@pytest.mark.parametrize(
    ("approve", "expected_status"),
    [(True, "succeeded"), (False, "failed")],
)
def test_simulates_selected_outcome(approve, expected_status):
    order_id = uuid4()

    result = simulate_payment(
        order_id,
        amount_minor=3998,
        currency="USD",
        approve=approve,
    )

    assert result.status == expected_status
    assert result.provider_reference == f"sim-{order_id}"


def test_repeated_simulation_has_same_result():
    order_id = uuid4()

    first = simulate_payment(order_id, 3998, "USD", approve=True)
    second = simulate_payment(order_id, 3998, "USD", approve=True)

    assert first == second


def test_simulator_rejects_negative_amount():
    with pytest.raises(
        PaymentValidationError,
        match="Payment amount must not be negative",
    ):
        simulate_payment(uuid4(), -1, "USD", approve=True)


def test_simulator_rejects_unsupported_currency():
    with pytest.raises(
        PaymentValidationError,
        match="Simulator supports USD only",
    ):
        simulate_payment(uuid4(), 3998, "EUR", approve=True)