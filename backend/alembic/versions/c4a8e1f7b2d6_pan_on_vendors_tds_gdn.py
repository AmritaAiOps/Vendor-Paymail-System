"""PAN on vendors, tds_records and gdn_records

Revision ID: c4a8e1f7b2d6
Revises: b7d2e8f1c3a9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a8e1f7b2d6'
down_revision: Union[str, Sequence[str], None] = 'b7d2e8f1c3a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("vendors", "tds_records", "gdn_records"):
        op.add_column(table, sa.Column("pan", sa.String(10), nullable=True))
    op.create_index("ix_vendors_pan", "vendors", ["pan"])


def downgrade() -> None:
    op.drop_index("ix_vendors_pan", table_name="vendors")
    for table in ("gdn_records", "tds_records", "vendors"):
        op.drop_column(table, "pan")
