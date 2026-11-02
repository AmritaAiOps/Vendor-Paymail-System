"""queue status DRAFT: emails wait for Send all before the T+2 job may send them

Revision ID: b7d2e8f1c3a9
Revises: a1f3c9d2e4b7
Create Date: 2026-11-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7d2e8f1c3a9'
down_revision: Union[str, Sequence[str], None] = 'a1f3c9d2e4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD = ("PENDING", "SENDING", "SENT", "FAILED", "SKIPPED")
NEW = ("DRAFT", *OLD)


def _allow(values: tuple) -> None:
    """Replace the QueueStatus CHECK constraint. Autogenerate can't see enum value changes."""
    with op.batch_alter_table("email_queue", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_email_queue_queuestatus"), type_="check")
        batch_op.create_check_constraint(op.f("ck_email_queue_queuestatus"),
                                         f"status IN ({', '.join(repr(v) for v in values)})")


def upgrade() -> None:
    """Upgrade schema. Emails already queued stay PENDING (scheduled), as before."""
    _allow(NEW)


def downgrade() -> None:
    """Downgrade schema. Drafts become PENDING: the T+2 job will send them."""
    op.execute("UPDATE email_queue SET status = 'PENDING' WHERE status = 'DRAFT'")
    _allow(OLD)
