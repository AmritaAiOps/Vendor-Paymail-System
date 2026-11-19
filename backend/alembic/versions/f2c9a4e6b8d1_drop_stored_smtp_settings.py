"""drop SMTP settings saved from the Settings page: the mail server now comes only from the environment

Revision ID: f2c9a4e6b8d1
Revises: e1b4a7c9d3f2

Also removes any SMTP password that was stored there in plain text.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f2c9a4e6b8d1'
down_revision: Union[str, Sequence[str], None] = 'e1b4a7c9d3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM app_settings WHERE key IN ('smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', "
               "'smtp_from', 'smtp_from_name', 'smtp_starttls')")


def downgrade() -> None:
    pass  # the rows were only overridden values; nothing to restore
