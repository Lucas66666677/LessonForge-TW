"""One-off data migration: copy every row from the old Render Postgres into
the new Supabase-hosted `lessonforge` schema, in FK-safe order.

Usage (run locally, never commit real credentials to this file):

    OLD_DATABASE_URL="postgresql://lessonforge:...@dpg-....render.com/lessonforge" \
    NEW_DATABASE_URL="postgresql://lessonforge_runtime.<project-ref>:...@aws-0-....pooler.supabase.com:5432/postgres" \
    python scripts/migrate_to_supabase.py

Safe to re-run: creates tables if missing, but does not delete or overwrite
existing rows in the destination (skips a table already containing rows,
so it won't double-insert on a second run).
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from lessonforge.database import Base, create_schema  # noqa: E402
from lessonforge import models  # noqa: E402,F401  (registers all tables on Base.metadata)


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def main() -> None:
    old_url = os.environ["OLD_DATABASE_URL"]
    new_url = os.environ["NEW_DATABASE_URL"]

    old_engine = create_async_engine(_normalize(old_url))
    new_engine = create_async_engine(_normalize(new_url))

    print("Creating tables in destination schema (no-op if they already exist)...")
    await create_schema(new_engine)

    total_copied = 0
    async with old_engine.connect() as old_conn, new_engine.begin() as new_conn:
        for table in Base.metadata.sorted_tables:
            existing = (await new_conn.execute(select(table).limit(1))).first()
            if existing is not None:
                print(f"  {table.name}: already has data, skipping")
                continue

            rows = (await old_conn.execute(select(table))).mappings().all()
            if not rows:
                print(f"  {table.name}: 0 rows")
                continue

            await new_conn.execute(table.insert(), [dict(row) for row in rows])
            print(f"  {table.name}: copied {len(rows)} rows")
            total_copied += len(rows)

    await old_engine.dispose()
    await new_engine.dispose()
    print(f"Done. {total_copied} total rows copied.")


if __name__ == "__main__":
    asyncio.run(main())
