import pytest
from pydantic import ValidationError

from app.schemas import OrderCreate


PRODUCT_ID = "b8f00bc2-b494-4c02-8cad-7ad0f3336290"


def test_accepts_valid_order():
    order = OrderCreate(
        items=[{"product_id": PRODUCT_ID, "quantity": 2}]
    )

    assert len(order.items) == 1
    assert order.items[0].quantity == 2


def test_rejects_empty_order():
    with pytest.raises(ValidationError):
        OrderCreate(items=[])


@pytest.mark.parametrize("quantity", [0, -1, 1001, 1.5, True, "2"])
def test_rejects_invalid_quantity(quantity):
    with pytest.raises(ValidationError):
        OrderCreate(
            items=[{"product_id": PRODUCT_ID, "quantity": quantity}]
        )


def test_rejects_client_supplied_price():
    with pytest.raises(ValidationError):
        OrderCreate(
            items=[
                {
                    "product_id": PRODUCT_ID,
                    "quantity": 2,
                    "price": 1,
                }
            ]
        )