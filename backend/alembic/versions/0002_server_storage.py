"""Add encrypted Supabase tokens, server sessions and domain storage."""
from alembic import op

revision = "0002_server_storage"
down_revision = "0001_users"
branch_labels = None
depends_on = None

def upgrade():
    op.execute('ALTER TABLE users ADD COLUMN nickname VARCHAR(20) COLLATE "C"')
    op.execute('ALTER TABLE users ADD CONSTRAINT uq_users_nickname UNIQUE (nickname)')
    op.execute('ALTER TABLE users ADD COLUMN session_window_start TIMESTAMP WITH TIME ZONE')
    op.execute('ALTER TABLE users ADD COLUMN session_issue_count INTEGER DEFAULT 0 NOT NULL')
    op.execute('\nCREATE TABLE auth_sessions (\n\thash VARCHAR(64) NOT NULL, \n\tuser_id UUID NOT NULL, \n\ttokens TEXT NOT NULL, \n\tcsrf VARCHAR(64) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlast_seen TIMESTAMP WITH TIME ZONE NOT NULL, \n\tchecked_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\ttoken_expires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (hash), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n')
    op.execute('CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at)')
    op.execute('CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id)')
    op.execute("\nCREATE TABLE trips (\n\tid VARCHAR(40) NOT NULL, \n\towner_id UUID NOT NULL, \n\tcontent JSON NOT NULL, \n\tsource_draft_id VARCHAR(100) NOT NULL, \n\tversion INTEGER DEFAULT '1' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_trip_version CHECK (version > 0), \n\tCONSTRAINT uq_trip_source_draft UNIQUE (owner_id, source_draft_id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n")
    op.execute('CREATE INDEX ix_trips_owner_id ON trips (owner_id)')
    op.execute('\nCREATE TABLE posts (\n\tid VARCHAR(40) NOT NULL, \n\ttrip_id VARCHAR(40) NOT NULL, \n\towner_id UUID NOT NULL, \n\tcontent JSON NOT NULL, \n\tpublished_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (trip_id), \n\tFOREIGN KEY(trip_id) REFERENCES trips (id) ON DELETE CASCADE, \n\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE post_hearts (\n\tpost_id VARCHAR(40) NOT NULL, \n\tuser_id UUID NOT NULL, \n\tPRIMARY KEY (post_id, user_id), \n\tFOREIGN KEY(post_id) REFERENCES posts (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE idempotency_keys (\n\tuser_id UUID NOT NULL, \n\tscope VARCHAR(100) NOT NULL, \n\tkey VARCHAR(128) NOT NULL, \n\tbody_hash VARCHAR(64) NOT NULL, \n\tresponse JSON NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (user_id, scope, key), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n')
    op.execute('CREATE INDEX ix_idempotency_keys_expires_at ON idempotency_keys (expires_at)')

def downgrade():
    op.execute('ALTER TABLE users DROP COLUMN IF EXISTS session_issue_count')
    op.execute('ALTER TABLE users DROP COLUMN IF EXISTS session_window_start')
    op.drop_table('idempotency_keys')
    op.drop_table('post_hearts')
    op.drop_table('posts')
    op.drop_table('trips')
    op.drop_table('auth_sessions')
    op.drop_column("users", "nickname")
