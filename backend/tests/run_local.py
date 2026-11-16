"""Disposable local PostgreSQL tests; never reads the application's DATABASE_URL."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
from cryptography.fernet import Fernet

os.chdir(Path(__file__).resolve().parents[1])
env = {**os.environ, 'SUPABASE_URL':'https://example.supabase.co', 'SUPABASE_PUBLISHABLE_KEY':'test',
       'FRONTEND_ORIGIN':'https://frontend.example', 'SESSION_ENCRYPTION_KEY':Fernet.generate_key().decode()}


async def prepare():
    conn = await asyncpg.connect('postgresql://postgres@127.0.0.1:55440/postgres', timeout=5)
    for database in ('tripick_test', 'tripick_test_fresh'):
        if not await conn.fetchval('select 1 from pg_database where datname=$1', database):
            await conn.execute('CREATE DATABASE ' + database)
    await conn.close()


asyncio.run(prepare())
for database in ('tripick_test', 'tripick_test_fresh'):
    env['DATABASE_URL'] = 'postgresql+asyncpg://postgres@127.0.0.1:55440/' + database
    if '--reset-test-schema' in sys.argv:
        subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', 'base'], env=env, check=True)
    if database == 'tripick_test' and '--reset-test-schema' in sys.argv:
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', '0001_users'], env=env, check=True)
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], env=env, check=True)
    subprocess.run([sys.executable, '-m', 'alembic', 'current'], env=env, check=True)
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'], env=env, check=True)
