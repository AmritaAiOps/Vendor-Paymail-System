"""queue status SENDING

Revision ID: 090624a192c0
Revises: 67f5d9b7f717
Create Date: 2026-10-30 11:52:13.900905

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '090624a192c0'
down_revision: Union[str, Sequence[str], None] = '67f5d9b7f717'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD = ("PENDING", "SENT", "FAILED", "SKIPPED")
NEW = ("PENDING", "SENDING", "SENT", "FAILED", "SKIPPED")


def _allow(values: tuple) -> None:
    """Replace the QueueStatus CHECK constraint. Autogenerate can't see enum value changes."""
    with op.batch_alter_table("email_queue", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_email_queue_queuestatus"), type_="check")
        batch_op.create_check_constraint(op.f("ck_email_queue_queuestatus"),
                                         f"status IN ({', '.join(repr(v) for v in values)})")


def upgrade() -> None:
    """Upgrade schema."""
    _allow(NEW)


def downgrade() -> None:
    """Downgrade schema. Fails if any email is still SENDING."""
    _allow(OLD)
