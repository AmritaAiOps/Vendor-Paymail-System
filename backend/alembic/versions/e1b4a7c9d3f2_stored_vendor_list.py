"""stored vendors list: is_active on vendors, vendor_list_state and vendor_list_history

Revision ID: e1b4a7c9d3f2
Revises: c4a8e1f7b2d6

Vendors already in the table (from earlier uploads) become the stored list, version 1, so nobody has to upload it again.
"""
from datetime import datetime
from typing import Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = 'e1b4a7c9d3f2'
down_revision: Union[str, Sequence[str], None] = 'c4a8e1f7b2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        "vendor_list_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor_list_state")),
    )
    op.create_table(
        "vendor_list_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("logged_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("user", sa.String(255), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("vendor_count", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor_list_history")),
    )
    op.create_index(op.f("ix_vendor_list_history_version"), "vendor_list_history", ["version"])

    bind = op.get_bind()
    count = bind.scalar(sa.text("SELECT COUNT(*) FROM vendors"))
    if count:
        name = bind.scalar(sa.text("SELECT vendors_file FROM upload_batches ORDER BY id DESC LIMIT 1")) or "(existing vendors)"
        now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)  # stored timestamps are IST wall-clock
        bind.execute(sa.text("INSERT INTO vendor_list_state (id, version, file_name, updated_at, updated_by) "
                             "VALUES (1, 1, :f, :t, 'system (migrated)')"), {"f": name, "t": now})
        bind.execute(sa.text("INSERT INTO vendor_list_history (version, user, action, file_name, vendor_count, added, removed, changed) "
                             "VALUES (1, 'system (migrated)', 'UPLOAD', :f, :n, :n, 0, 0)"), {"f": name, "n": count})


def downgrade() -> None:
    op.drop_index(op.f("ix_vendor_list_history_version"), table_name="vendor_list_history")
    op.drop_table("vendor_list_history")
    op.drop_table("vendor_list_state")
    op.execute("DELETE FROM vendors WHERE NOT is_active AND id NOT IN (SELECT vendor_id FROM reconciliation_results WHERE vendor_id IS NOT NULL) "
               "AND id NOT IN (SELECT vendor_id FROM email_queue)")
    with op.batch_alter_table("vendors") as batch_op:
        batch_op.drop_column("is_active")
