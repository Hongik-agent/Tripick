"""Record bounded generation jobs, verified drafts and request counters."""
from alembic import op
import sqlalchemy as sa

revision = "0006_generation_jobs"
down_revision = "0005_remove_party_flags"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("generation_jobs",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("cost_krw", sa.Integer, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("content", sa.JSON))
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_created_at", "generation_jobs", ["created_at"])
    op.create_table("generation_requests",
        sa.Column("key", sa.String(90), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer, nullable=False))


def downgrade():
    op.drop_table("generation_requests")
    op.drop_table("generation_jobs")
