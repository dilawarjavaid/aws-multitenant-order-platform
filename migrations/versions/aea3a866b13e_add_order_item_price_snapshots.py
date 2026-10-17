"""add order item price snapshots

Revision ID: aea3a866b13e
Revises: b983836dbdb3
Create Date: 2026-10-17 23:06:36.880174
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aea3a866b13e"
down_revision: Union[str, Sequence[str], None] = "b983836dbdb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "order_items",
        sa.Column("unit_price_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "order_items",
        sa.Column("currency", sa.String(length=3), nullable=True),
    )

    op.create_check_constraint(
        "ck_order_items_price",
        "order_items",
        "unit_price_minor IS NULL OR unit_price_minor >= 0",
    )
    op.create_check_constraint(
        "ck_order_items_price_currency",
        "order_items",
        "(unit_price_minor IS NULL AND currency IS NULL) OR "
        "(unit_price_minor IS NOT NULL AND currency IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_order_items_price_currency",
        "order_items",
        type_="check",
    )
    op.drop_constraint(
        "ck_order_items_price",
        "order_items",
        type_="check",
    )

    op.drop_column("order_items", "currency")
    op.drop_column("order_items", "unit_price_minor")