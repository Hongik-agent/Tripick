from sqlalchemy import Column, DateTime, MetaData, String, Table, Uuid, func, ForeignKey, Integer, Text, JSON, CheckConstraint, UniqueConstraint


metadata = MetaData()

generation_models = Table("generation_models", metadata,
    Column("id", Text, primary_key=True),
)

oauth_transactions = Table("oauth_transactions", metadata,
    Column("state_hash", String(64), primary_key=True),
    Column("browser_hash", String(64), nullable=False, index=True),
    Column("verifier", Text, nullable=True),
    Column("provider", String(10), nullable=False),
    Column("return_to", String(10), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
)

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", String(320), nullable=True),
    Column("nickname", String(20, collation="C"), unique=True),
    Column("session_window_start", DateTime(timezone=True)),
    Column("session_issue_count", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

auth_sessions = Table("auth_sessions", metadata,
    Column("hash", String(64), primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("tokens", Text, nullable=False),
    Column("csrf", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_seen", DateTime(timezone=True), nullable=False),
    Column("checked_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("token_expires_at", DateTime(timezone=True), nullable=False),
)
trips = Table("trips", metadata,
    Column("id", String(40), primary_key=True),
    Column("owner_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("content", JSON, nullable=False),
    Column("source_draft_id", String(100), nullable=False),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("version > 0", name="ck_trip_version"),
    UniqueConstraint("owner_id", "source_draft_id", name="uq_trip_source_draft"),
)
posts = Table("posts", metadata,
    Column("id", String(40), primary_key=True),
    Column("trip_id", String(40), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("owner_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("content", JSON, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
post_hearts = Table("post_hearts", metadata,
    Column("post_id", String(40), ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
idempotency_keys = Table("idempotency_keys", metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("scope", String(100), primary_key=True),
    Column("key", String(128), primary_key=True),
    Column("body_hash", String(64), nullable=False),
    Column("response", JSON, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
)

generation_jobs = Table("generation_jobs", metadata,
    Column("id", String(40), primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("fingerprint", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("status", String(12), nullable=False),
    Column("error_code", String(64)),
    Column("cost_krw", Integer, nullable=False),
    Column("input_tokens", Integer, nullable=False, server_default="0"),
    Column("output_tokens", Integer, nullable=False, server_default="0"),
    Column("version", Integer, nullable=False, server_default="1"),
    Column("content", JSON),
)

generation_requests = Table("generation_requests", metadata,
    Column("key", String(90), primary_key=True),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("count", Integer, nullable=False),
)
