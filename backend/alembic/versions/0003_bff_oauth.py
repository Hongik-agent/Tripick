"""Add one-use, browser-bound OAuth PKCE transactions."""
from alembic import op
import sqlalchemy as sa

revision = "0003_bff_oauth"
down_revision = "0002_server_storage"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("oauth_transactions",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(10), nullable=False),
        sa.Column("return_to", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_oauth_transactions_browser_hash", "oauth_transactions", ["browser_hash"])
    op.create_index("ix_oauth_transactions_expires_at", "oauth_transactions", ["expires_at"])


def downgrade():
    op.drop_table("oauth_transactions")
