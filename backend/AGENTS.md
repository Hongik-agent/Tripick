# Tripick

## Backend

- Keep backend environment variable loading, names, defaults, and validation in `app/config.py`. Other backend modules import settings from that module; do not read environment variables or `.env` independently.
- Store local credentials only in the ignored `.env`. Keep `.env.example` free of secrets and update it when adding a required setting.
- Keep database access async with SQLAlchemy and asyncpg. Use Alembic for schema changes; its offline mode must run without loading database credentials.
- Follow the PRD's `[CONFIRMED]` decisions. Treat `[PROPOSED]` and `[OPEN]` items as decisions to resolve before implementation.
