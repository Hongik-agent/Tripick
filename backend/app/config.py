import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

database_url = os.environ["DATABASE_URL"]
supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
supabase_publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
