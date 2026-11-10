import os
import io
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.error import HTTPError
from uuid import uuid4

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers


os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-key")
os.environ.setdefault("FRONTEND_ORIGIN", "https://frontend.example")

from app import main  # noqa: E402


class CorsTest(unittest.TestCase):
    def test_configured_frontend_can_put_with_authorization(self) -> None:
        cors = main.app.build_middleware_stack().app.app
        self.assertIsInstance(cors, CORSMiddleware)
        response = cors.preflight_response(
            Headers(
                {
                    "origin": main.frontend_origin,
                    "access-control-request-method": "PUT",
                    "access-control-request-headers": "authorization",
                }
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], main.frontend_origin)


class AuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_google_user_is_saved_from_verified_identity(self) -> None:
        user_id = uuid4()
        identity = {
            "id": str(user_id),
            "email": "traveler@example.com",
            "app_metadata": {"providers": ["google"]},
        }
        transaction = AsyncMock()
        connection = AsyncMock()
        transaction.__aenter__.return_value = connection

        with patch.object(main.asyncio, "to_thread", new=AsyncMock(return_value=identity)), patch.object(
            main, "engine", Mock(begin=lambda: transaction)
        ):
            result = await main.sync_user("Bearer verified-token")

        self.assertEqual(result, {"id": str(user_id), "email": "traveler@example.com"})
        statement = connection.execute.await_args.args[0]
        self.assertIn("ON CONFLICT", str(statement))
        self.assertEqual(statement.compile().params["id"], user_id)

    async def test_missing_token_is_rejected_before_database_access(self) -> None:
        with self.assertRaises(HTTPException) as error:
            await main.sync_user(None)
        self.assertEqual(error.exception.status_code, 401)

    async def test_unapproved_provider_cannot_create_account(self) -> None:
        identity = {"id": str(uuid4()), "email": None, "app_metadata": {"providers": ["email"]}}
        with patch.object(main.asyncio, "to_thread", new=AsyncMock(return_value=identity)):
            with self.assertRaises(HTTPException) as error:
                await main.sync_user("Bearer verified-token")
        self.assertEqual(error.exception.status_code, 403)

    async def test_kakao_account_without_email_is_supported(self) -> None:
        user_id = uuid4()
        identity = {"id": str(user_id), "email": None, "app_metadata": {"providers": ["kakao"]}}
        transaction = AsyncMock()
        transaction.__aenter__.return_value = AsyncMock()
        with patch.object(main.asyncio, "to_thread", new=AsyncMock(return_value=identity)), patch.object(
            main, "engine", Mock(begin=lambda: transaction)
        ):
            result = await main.sync_user("Bearer verified-token")
        self.assertEqual(result, {"id": str(user_id), "email": None})

    def test_supabase_rejects_invalid_token(self) -> None:
        with patch.object(main, "urlopen", side_effect=HTTPError("url", 401, "", {}, None)):
            with self.assertRaises(HTTPException) as error:
                main.supabase_user("invalid-token")
        self.assertEqual(error.exception.status_code, 401)

    def test_supabase_response_is_read_from_verified_endpoint(self) -> None:
        payload = {"id": str(uuid4()), "app_metadata": {"providers": ["google"]}}
        with patch.object(main, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            self.assertEqual(main.supabase_user("sample-token"), payload)
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.supabase.co/auth/v1/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer sample-token")


if __name__ == "__main__":
    unittest.main()
