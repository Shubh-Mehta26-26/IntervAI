"""Allow topic learning without inventing knowledge gaps; persist self-checks."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8e2d4519a06"
down_revision = "9ad2c4f7b611"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("learning_items", "target_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("learning_items", sa.Column("check_result", postgresql.JSONB(), nullable=True))


def downgrade():
    # Refuse a lossy rollback when real self-directed learning data exists.
    count = op.get_bind().scalar(sa.text("SELECT count(*) FROM learning_items WHERE target_id IS NULL"))
    if count:
        raise RuntimeError("Export or explicitly remove guided plans before downgrading learning storage.")
    op.drop_column("learning_items", "check_result")
    op.alter_column("learning_items", "target_id", existing_type=sa.Uuid(), nullable=False)
