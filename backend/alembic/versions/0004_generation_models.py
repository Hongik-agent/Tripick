"""Register the model IDs available for itinerary generation."""
from alembic import op
import sqlalchemy as sa

revision = "0004_generation_models"
down_revision = "0003_bff_oauth"
branch_labels = None
depends_on = None


def upgrade():
    models = op.create_table("generation_models",
        sa.Column("id", sa.Text(), primary_key=True))
    op.bulk_insert(models, [{"id": "gpt-6-luna"}, {"id": "gpt-6.1-terra"}])


def downgrade():
    op.drop_table("generation_models")
