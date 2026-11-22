"""Remove retired companion flags from saved trip JSON."""
from alembic import op

revision = "0005_remove_party_flags"
down_revision = "0004_generation_models"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE trips
        SET content = (content::jsonb
            #- '{conditions,party,withChildren}'
            #- '{conditions,party,withSeniors}')::json
        WHERE json_typeof(content #> '{conditions,party}') = 'object'
          AND (content #> '{conditions,party}')::jsonb ?| ARRAY['withChildren', 'withSeniors']
    """)


def downgrade():
    # Deleted user values cannot be reconstructed.
    pass
