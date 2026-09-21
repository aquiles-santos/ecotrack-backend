"""create alerts and reading_cache

Revision ID: d92649645886
Revises:
Create Date: 2026-09-21 22:51:51.788875

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d92649645886"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("local_name", sa.String(length=255), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=False),
        sa.Column(
            "target_pollutant",
            sa.Enum(
                "PM2.5",
                "PM10",
                "CO",
                "NO2",
                "O3",
                name="target_pollutant_enum",
            ),
            nullable=False,
        ),
        sa.Column(
            "concentration_limit",
            sa.Numeric(precision=12, scale=4),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reading_cache",
        sa.Column("lat", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("lon", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("aqi", sa.Integer(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("lat", "lon"),
    )


def downgrade() -> None:
    op.drop_table("reading_cache")
    op.drop_table("alerts")
    sa.Enum(name="target_pollutant_enum").drop(op.get_bind(), checkfirst=True)
