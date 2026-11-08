import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from .config import supabase_publishable_key, supabase_url
from .db import engine
from .models import users


app = FastAPI(title="Tripick API")


def supabase_user(token: str) -> dict:
    request = Request(
        f"{supabase_url}/auth/v1/user",
        headers={"apikey": supabase_publishable_key, "Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(status_code=401, detail="invalid session") from exc
        raise HTTPException(status_code=502, detail="authentication service unavailable") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="authentication service unavailable") from exc


@app.put("/api/users/me")
async def sync_user(authorization: str | None = Header(default=None)) -> dict[str, str | None]:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token or len(token) > 8192:
        raise HTTPException(status_code=401, detail="invalid session")

    identity = await asyncio.to_thread(supabase_user, token)
    try:
        user_id = UUID(identity["id"])
        email = identity.get("email")
        providers = identity["app_metadata"]["providers"]
        if email is not None and (not isinstance(email, str) or len(email) > 320):
            raise ValueError("invalid email")
        if not isinstance(providers, list) or not any(
            provider in ("google", "kakao") for provider in providers
        ):
            raise HTTPException(status_code=403, detail="unsupported login provider")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="invalid authentication response") from exc

    statement = insert(users).values(id=user_id, email=email)
    statement = statement.on_conflict_do_update(
        index_elements=[users.c.id], set_={"email": statement.excluded.email}
    )
    try:
        async with engine.begin() as connection:
            await connection.execute(statement)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"id": str(user_id), "email": email}


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}
