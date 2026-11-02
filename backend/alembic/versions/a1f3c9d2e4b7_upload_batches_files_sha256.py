"""upload_batches.files_sha256: refuse the same five files twice

Revision ID: a1f3c9d2e4b7
Revises: 090624a192c0
Create Date: 2026-11-02 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f3c9d2e4b7'
down_revision: Union[str, Sequence[str], None] = '090624a192c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Existing batches keep NULL: only uploads from now on are checked."""
    with op.batch_alter_table('upload_batches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('files_sha256', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_upload_batches_files_sha256'), ['files_sha256'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('upload_batches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_upload_batches_files_sha256'))
        batch_op.drop_column('files_sha256')
