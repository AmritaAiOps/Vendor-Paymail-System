"""bounced payments

Revision ID: 8c034147301c
Revises: 7ba642906236
Create Date: 2026-10-30 11:03:31.286671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c034147301c'
down_revision: Union[str, Sequence[str], None] = '7ba642906236'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = ("UTR_NOT_FOUND", "VENDOR_NOT_FOUND", "INVALID_EMAIL", "REASON_MISSING")
NEW = OLD + ("BOUNCED",)
CHECKED = (("reconciliation_results", "exception_type"), ("email_history", "not_sent_reason"))


def _allow(values: tuple) -> None:
    """Replace the ExceptionType CHECK constraint on both columns. Autogenerate can't see enum value changes."""
    for table, column in CHECKED:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(op.f(f"ck_{table}_exceptiontype"), type_="check")
            batch_op.create_check_constraint(op.f(f"ck_{table}_exceptiontype"),
                                             f"{column} IN ({', '.join(repr(v) for v in values)})")
    if op.get_bind().dialect.name == "sqlite":
        # batch mode rebuilt email_history, which drops its append-only triggers: put them back
        for action in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER IF EXISTS email_history_no_{action.lower()}")
            op.execute(f"""CREATE TRIGGER email_history_no_{action.lower()} BEFORE {action} ON email_history
                BEGIN SELECT RAISE(ABORT, 'email_history is append-only'); END""")


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_bounced', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('bounce_note', sa.Text(), nullable=True))
    _allow(NEW)


def downgrade() -> None:
    """Downgrade schema. Fails if any row already uses BOUNCED."""
    _allow(OLD)
    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.drop_column('bounce_note')
        batch_op.drop_column('is_bounced')
