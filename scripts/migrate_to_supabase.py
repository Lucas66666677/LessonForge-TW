"""One-off data migration: copy every row from the old Render Postgres into
the new Supabase-hosted `lessonforge` schema, in FK-safe order.

Usage (run locally, never commit real credentials to this file):

    OLD_DATABASE_URL="postgresql://lessonforge:...@dpg-....render.com/lessonforge" \
    NEW_DATABASE_URL="postgresql://lessonforge_runtime.<project-ref>:...@aws-0-....pooler.supabase.com:5432/postgres" \
    python scripts/migrate_to_supabase.py

Pass ``--dry-run`` first to check both connections, confirm the destination
schema is not left over from a half-finished attempt, and print the row counts
a real run would copy -- without creating or writing anything.

Safe to re-run: creates tables if missing, but does not delete or overwrite
existing rows in the destination (skips a table already containing rows,
so it won't double-insert on a second run). After copying, every table it
wrote is counted again on a fresh connection and the run fails loudly if any
count disagrees, so ``DATABASE_URL`` is never switched over on the strength of
"the inserts did not raise".
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from lessonforge import models  # noqa: E402,F401  (registers all tables on Base.metadata)
from lessonforge.database import Base  # noqa: E402

DESTINATION_SCHEMA = "lessonforge"


def _normalize(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


ESCAPED_FOREIGN_KEY_SQL = """
SELECT c.relname  AS table_name,
       fn.nspname AS referenced_schema,
       f.relname  AS referenced_table
FROM pg_constraint con
JOIN pg_class c      ON c.oid = con.conrelid
JOIN pg_namespace n  ON n.oid = c.relnamespace
JOIN pg_class f      ON f.oid = con.confrelid
JOIN pg_namespace fn ON fn.oid = f.relnamespace
WHERE con.contype = 'f'
  AND n.nspname = :schema
  AND fn.nspname <> :schema
ORDER BY c.relname
"""


async def assert_destination_is_sane(connection) -> None:
    """Refuse to run on top of a half-finished earlier attempt.

    An interrupted run can leave tables whose foreign keys were resolved
    against `public` (another product's schema on this shared project) rather
    than against our own. Those tables look present to `checkfirst`, so a
    re-run would quietly build on them and copy rows into a graph that points
    at data we do not own. Better to stop and say exactly how to reset.
    """
    escaped = (
        await connection.execute(
            text(ESCAPED_FOREIGN_KEY_SQL), {"schema": DESTINATION_SCHEMA}
        )
    ).mappings().all()
    if not escaped:
        return

    details = "\n".join(
        f"  - {row['table_name']} -> "
        f"{row['referenced_schema']}.{row['referenced_table']}"
        for row in escaped
    )
    raise RuntimeError(
        f"Schema {DESTINATION_SCHEMA!r} contains tables whose foreign keys point "
        f"outside it, which means an earlier run was interrupted part-way:\n"
        f"{details}\n\n"
        f"Reset the destination and run this again:\n"
        f"  DROP SCHEMA {DESTINATION_SCHEMA} CASCADE;\n"
        f"  CREATE SCHEMA {DESTINATION_SCHEMA};\n"
        f"  GRANT USAGE, CREATE ON SCHEMA {DESTINATION_SCHEMA} "
        f"TO lessonforge_runtime;"
    )


async def _count(connection, table) -> int:
    return int(
        (await connection.execute(select(func.count()).select_from(table))).scalar_one()
    )


async def dry_run(old_engine, destination_engine) -> None:
    """Report what a real run would do, without creating or writing anything."""

    print("DRY RUN -- nothing will be created, inserted, or modified.\n")
    async with destination_engine.connect() as new_conn:
        await new_conn.execute(text("SET LOCAL search_path TO lessonforge, public"))
        await assert_destination_is_sane(new_conn)
        inspector_tables = set(
            (
                await new_conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname = :schema"
                    ),
                    {"schema": DESTINATION_SCHEMA},
                )
            )
            .scalars()
            .all()
        )

    total_source = 0
    async with old_engine.connect() as old_conn:
        for table in Base.metadata.sorted_tables:
            source_rows = await _count(old_conn, table)
            total_source += source_rows
            state = "exists" if table.name in inspector_tables else "to create"
            print(f"  {table.name:<32} {source_rows:>7} rows in source  ({state})")

    print(
        f"\nWould copy {total_source} rows across "
        f"{len(Base.metadata.sorted_tables)} tables into "
        f"{DESTINATION_SCHEMA!r}."
    )


async def main() -> None:
    old_url = os.environ["OLD_DATABASE_URL"]
    new_url = os.environ["NEW_DATABASE_URL"]

    old_engine = create_async_engine(_normalize(old_url))
    new_engine = create_async_engine(_normalize(new_url))
    destination_engine = new_engine.execution_options(
        schema_translate_map={None: DESTINATION_SCHEMA}
    )

    if "--dry-run" in sys.argv:
        try:
            await dry_run(old_engine, destination_engine)
        finally:
            await old_engine.dispose()
            await new_engine.dispose()
        return

    print(f"Creating tables in destination schema {DESTINATION_SCHEMA!r}...")
    async with destination_engine.begin() as connection:
        # Keep pgvector's unqualified `vector` type resolvable from `public`,
        # while schema_translate_map renders every application table with an
        # explicit `lessonforge.` prefix. This avoids mistaking a same-named
        # table in another product schema for the migration destination.
        await connection.execute(text("SET LOCAL search_path TO lessonforge, public"))
        await assert_destination_is_sane(connection)
        await connection.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True)
        )

    total_copied = 0
    copied_tables = []
    async with old_engine.connect() as old_conn, destination_engine.begin() as new_conn:
        await new_conn.execute(text("SET LOCAL search_path TO lessonforge, public"))
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
            copied_tables.append((table, len(rows)))
            total_copied += len(rows)

    # Read the destination back on a fresh connection, after the copy
    # transaction committed, and prove each table really holds what we think it
    # does. This is a one-shot migration of live data -- "the inserts did not
    # raise" is weaker evidence than counting the rows that landed.
    print("\nVerifying destination row counts...")
    mismatches = []
    async with destination_engine.connect() as verify_conn:
        await verify_conn.execute(text("SET LOCAL search_path TO lessonforge, public"))
        for table, expected in copied_tables:
            actual = await _count(verify_conn, table)
            if actual != expected:
                mismatches.append((table.name, expected, actual))
                print(f"  {table.name}: MISMATCH expected {expected}, found {actual}")
            else:
                print(f"  {table.name}: {actual} rows OK")

    await old_engine.dispose()
    await new_engine.dispose()

    if mismatches:
        raise RuntimeError(
            "Destination row counts do not match what was copied: "
            + ", ".join(
                f"{name} expected {expected} found {actual}"
                for name, expected, actual in mismatches
            )
            + ". Do not switch DATABASE_URL over until this is understood."
        )
    print(f"\nDone. {total_copied} rows copied and verified.")


if __name__ == "__main__":
    asyncio.run(main())
