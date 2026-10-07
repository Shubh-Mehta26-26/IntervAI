"""Foundation baseline; domain tables begin in Phase 2."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Extension is provisioned by a DB administrator/bootstrap, not runtime credentials.
    op.execute("SELECT 1")


def downgrade():
    # Shared extensions must not be dropped by an application downgrade.
    pass
