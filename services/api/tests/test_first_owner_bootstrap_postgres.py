"""Two bootstraps at once, on the database production actually runs.

`test_first_owner_bootstrap.py` pins the ordering and the refusal with a
recording stand-in, because SQLite has no advisory lock and cannot show mutual
exclusion at all. That left the claim that matters unproven: that two operators
running `--create` at the same moment end up with exactly one owner.

These tests run against a real PostgreSQL and answer it directly. They are
skipped unless `BOOTSTRAP_TEST_POSTGRES_URL` names a disposable database -- CI
starts a throwaway container for it -- so the ordinary suite is unaffected.

## The control test is the point

A concurrency test that passes is weak evidence on its own: it would also pass
if the two attempts never actually overlapped, and it would keep passing if the
lock were deleted but the race happened not to materialise. So
`test_without_the_lock_the_same_race_produces_two_owners` runs the identical
schedule with the lock removed and asserts the damage: two owners, two
organizations. It is the reason to believe the locked case proves anything.

Both races are made deterministic with barriers rather than left to timing, so
neither is a coin flip that happens to land right on CI.

## Safety

The harness refuses any database that is not local and not named as a test
database, because these tests TRUNCATE. No production database and no account
is involved, and there is no credential to leak: the CI container runs with
`POSTGRES_HOST_AUTH_METHOD=trust`, reachable only from the runner that is
destroyed with it, so nothing password-shaped is written down anywhere.

## One dependency worth naming

The guard needs READ COMMITTED, which is PostgreSQL's default. Under
REPEATABLE READ the waiting run's snapshot would predate the winner's commit,
so it would acquire the lock, still see zero owners, and create a second one --
the lock would hold and the invariant would break anyway.
`test_the_guard_depends_on_read_committed` pins it so that a future change to
the isolation level fails here rather than in production.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from lessonforge.database import Base
from lessonforge.models import Membership, Organization, User
from lessonforge.schemas import Role
from lessonforge.security import hash_password

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_bootstrap():
    path = REPO_ROOT / "scripts" / "bootstrap_owner.py"
    spec = importlib.util.spec_from_file_location("_lessonforge_bootstrap_owner_pg", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()

#: Names a disposable PostgreSQL. Absent everywhere except the CI job that
#: starts one, which is why these tests skip rather than fail by default.
POSTGRES_URL_ENV_VAR = "BOOTSTRAP_TEST_POSTGRES_URL"

#: Local fixture, never a real credential.
OWNER_PASSWORD = "local-test-owner-password"

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class NotADisposableDatabase(RuntimeError):
    """The harness was pointed somewhere it must not truncate."""


def require_disposable_url(raw: str):
    """Refuse anything that could be somebody's real database.

    These tests truncate three tables, so pointing them at the wrong URL is
    destructive in a way no assertion could undo afterwards. Two conditions,
    both cheap and both hard to satisfy by accident: the server must be local,
    and the database must be named as a test database. A container started by
    the CI job satisfies both; a deployed database satisfies neither.
    """

    url = make_url(raw)
    if url.host not in LOCAL_HOSTS:
        raise NotADisposableDatabase(
            f"{url.host!r} is not localhost. These tests TRUNCATE; they may only "
            f"run against a throwaway database on this machine."
        )
    if "test" not in (url.database or ""):
        raise NotADisposableDatabase(
            f"database {url.database!r} is not named as a test database. Rename it "
            f"so that truncating it cannot be a mistake."
        )
    return url


requires_postgres = pytest.mark.skipif(
    not os.environ.get(POSTGRES_URL_ENV_VAR),
    reason=f"set {POSTGRES_URL_ENV_VAR} to a disposable PostgreSQL to run these",
)


def _create_bootstrap_tables(connection) -> None:
    """Only the three tables the bootstrap touches.

    Building the whole schema would drag in pgvector for columns this code
    never reads, so the container stays a plain `postgres` image. The migration
    contract is covered separately by `test_migration_contract.py`.
    """

    Base.metadata.create_all(
        connection,
        tables=[Organization.__table__, User.__table__, Membership.__table__],
    )


@pytest_asyncio.fixture
async def pg_sessions():
    """A sessionmaker over the disposable database, emptied before each test."""

    url = require_disposable_url(os.environ[POSTGRES_URL_ENV_VAR])
    # A bug in the locking would otherwise show up as a job that hangs until the
    # workflow timeout kills it, with nothing to read. These turn that into a
    # fast, named failure: the lock wait is milliseconds when it is working.
    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"lock_timeout": "15s", "statement_timeout": "30s"}},
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_create_bootstrap_tables)
            await connection.execute(
                text("TRUNCATE memberships, users, organizations RESTART IDENTITY CASCADE")
            )
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()


async def _lock_is_free(pg_sessions) -> bool:
    """Ask a separate connection whether the bootstrap lock could be taken.

    `pg_try_advisory_xact_lock` answers immediately instead of waiting, and the
    rollback gives back whatever it just took, so this observes the lock
    without disturbing it. Asking the database beats reading `pg_locks`: it
    tests the property the bootstrap depends on rather than the catalog's
    encoding of a 64-bit key.
    """

    async with pg_sessions() as probe:
        acquired = await probe.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": bootstrap.BOOTSTRAP_LOCK_KEY},
        )
        await probe.rollback()
        return bool(acquired)


async def _owner_count(pg_sessions) -> int:
    async with pg_sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.role == Role.owner.value)
            )
            or 0
        )


# --------------------------------------------------------------------------- #
# The safety guard, checked everywhere -- not only where PostgreSQL exists
# --------------------------------------------------------------------------- #


def test_the_harness_refuses_a_database_it_must_not_truncate() -> None:
    """The guard has to hold on the machine that has no PostgreSQL too.

    It is the only thing standing between a mistyped environment variable and
    a truncated database, so it is not behind the skip.
    """

    with pytest.raises(NotADisposableDatabase, match="localhost"):
        require_disposable_url("postgresql+asyncpg://u:p@db.example.com:5432/lessonforge_test")

    with pytest.raises(NotADisposableDatabase, match="test database"):
        require_disposable_url("postgresql+asyncpg://u:p@127.0.0.1:5432/lessonforge")

    # Guards the guard: the shape CI uses must actually be accepted.
    accepted = require_disposable_url(
        "postgresql+asyncpg://u:p@127.0.0.1:5432/lessonforge_bootstrap_test"
    )
    assert accepted.database == "lessonforge_bootstrap_test"


# --------------------------------------------------------------------------- #
# The lock, against a real server
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_the_lock_is_really_held_and_released_by_rollback(pg_sessions) -> None:
    """The stand-in proves the statement is issued; this proves it does something."""

    assert await _lock_is_free(pg_sessions), "the lock was already held before the test"

    async with pg_sessions() as session:
        assert await bootstrap.hold_bootstrap_lock(session) is True
        assert not await _lock_is_free(
            pg_sessions
        ), "a second connection took the lock while the first was holding it"
        await session.rollback()

    assert await _lock_is_free(pg_sessions), "rollback did not release the lock"


@requires_postgres
async def test_a_committed_bootstrap_releases_the_lock(pg_sessions) -> None:
    """Transaction scope, observed: the commit is what gives the lock back."""

    async with pg_sessions() as session:
        await bootstrap.create_first_owner(
            session,
            email="owner@example.com",
            display_name="First Owner",
            organization_name="Bootstrap Academy",
            password=OWNER_PASSWORD,
        )

    assert await _lock_is_free(pg_sessions)
    assert await _owner_count(pg_sessions) == 1


@requires_postgres
async def test_a_run_that_dies_between_the_lock_and_the_commit_leaves_nothing_held(
    pg_sessions,
) -> None:
    """The claim in the script's docstring, checked rather than asserted.

    A session-scoped lock would survive this and block every later bootstrap
    until the connection was reaped. A transaction-scoped one cannot.
    """

    with pytest.raises(RuntimeError, match="simulated"):
        async with pg_sessions() as session:
            await bootstrap.hold_bootstrap_lock(session)
            assert not await _lock_is_free(pg_sessions)
            raise RuntimeError("simulated crash between the lock and the commit")

    assert await _lock_is_free(pg_sessions), "an abandoned run left the lock held"

    # And the next operator is not locked out by it.
    async with pg_sessions() as session:
        await bootstrap.create_first_owner(
            session,
            email="owner@example.com",
            display_name="First Owner",
            organization_name="Bootstrap Academy",
            password=OWNER_PASSWORD,
        )
    assert await _owner_count(pg_sessions) == 1


@requires_postgres
async def test_a_refused_bootstrap_releases_the_lock_for_the_next_one(pg_sessions) -> None:
    """A refusal is a rollback, not a leak.

    The duplicate-email refusal happens after the lock is taken, so it is the
    path where a leak would show up.
    """

    async with pg_sessions() as session:
        session.add(
            User(
                email="taken@example.com",
                display_name="Taken",
                password_hash=hash_password(OWNER_PASSWORD),
            )
        )
        await session.commit()

    async with pg_sessions() as session:
        with pytest.raises(bootstrap.BootstrapError, match="already exists"):
            await bootstrap.create_first_owner(
                session,
                email="taken@example.com",
                display_name="Taken",
                organization_name="Bootstrap Academy",
                password=OWNER_PASSWORD,
            )
        await session.rollback()

    assert await _lock_is_free(pg_sessions)
    assert await _owner_count(pg_sessions) == 0


# --------------------------------------------------------------------------- #
# Two operators, at the same moment
# --------------------------------------------------------------------------- #


@requires_postgres
async def test_the_guard_depends_on_read_committed(pg_sessions) -> None:
    """Name the assumption, so changing it fails here instead of in production.

    The lock serialises the two runs, but what makes the second one *refuse* is
    seeing the owner the first one committed. Under REPEATABLE READ its
    snapshot is taken when its first statement begins -- before the winner
    commits -- so it would wait for the lock, still read zero owners, and
    create a second one. The lock would be working and the invariant would
    break anyway.
    """

    async with pg_sessions() as session:
        level = await session.scalar(text("SHOW transaction_isolation"))

    assert level == "read committed", (
        f"isolation is {level!r}; the bootstrap's refusal depends on the waiting "
        f"run seeing the winner's commit, which only READ COMMITTED guarantees"
    )


@requires_postgres
async def test_two_concurrent_bootstraps_create_exactly_one_owner(pg_sessions) -> None:
    """The regression this whole file exists for.

    Both attempts open their transaction, meet at a barrier, and only then
    call `--create`, so the race is between the two bootstraps rather than
    between two connection checkouts. With the lock in place one waits, sees
    the owner the other created, and refuses.
    """

    barrier = asyncio.Barrier(2)

    async def attempt(email: str, organization_name: str) -> tuple[str, str]:
        async with pg_sessions() as session:
            await session.execute(text("SELECT 1"))
            await barrier.wait()
            try:
                await bootstrap.create_first_owner(
                    session,
                    email=email,
                    display_name="Owner",
                    organization_name=organization_name,
                    password=OWNER_PASSWORD,
                )
                return "created", ""
            except bootstrap.BootstrapError as error:
                await session.rollback()
                return "refused", str(error)

    results = await asyncio.gather(
        attempt("first@example.com", "First Academy"),
        attempt("second@example.com", "Second Academy"),
    )

    assert sorted(outcome for outcome, _ in results) == ["created", "refused"], results

    refusal = next(detail for outcome, detail in results if outcome == "refused")
    assert "owner membership already exists" in refusal, (
        "the loser must refuse because it saw the winner's owner, not because the "
        f"database raised something else: {refusal}"
    )

    async with pg_sessions() as session:
        counts = await bootstrap.read_status(session)
    assert counts["owner_memberships"] == 1
    assert counts["users"] == 1
    assert counts["organizations"] == 1

    assert await _lock_is_free(pg_sessions), "the race left the lock held"


@requires_postgres
async def test_without_the_lock_the_same_race_produces_two_owners(pg_sessions) -> None:
    """The control, and the reason the test above is worth anything.

    This is `create_first_owner`'s check-then-write with the lock left out,
    run on the same schedule against the same server. If this stopped
    producing two owners, the locked test would be passing for a reason other
    than the lock -- so the failure that matters is this one turning green.

    Two barriers make the interleaving certain rather than likely: both
    attempts finish counting before either starts writing, which is exactly
    what the advisory lock makes impossible.
    """

    counted = asyncio.Barrier(2)
    before_writing = asyncio.Barrier(2)
    # Hashed once, outside the race: argon2 is slow enough to skew the timing.
    password_hash = hash_password(OWNER_PASSWORD)

    async def unlocked_attempt(email: str, organization_name: str) -> str:
        async with pg_sessions() as session:
            await session.execute(text("SELECT 1"))
            await counted.wait()

            existing = await session.scalar(
                select(func.count())
                .select_from(Membership)
                .where(Membership.role == Role.owner.value)
            )
            await before_writing.wait()
            if existing:
                await session.rollback()
                return "refused"

            organization = Organization(
                name=organization_name, slug=bootstrap.slugify(organization_name)
            )
            session.add(organization)
            await session.flush()
            user = User(email=email, display_name="Owner", password_hash=password_hash)
            session.add(user)
            await session.flush()
            session.add(
                Membership(
                    organization_id=organization.id, user_id=user.id, role=Role.owner.value
                )
            )
            await session.commit()
            return "created"

    outcomes = await asyncio.gather(
        unlocked_attempt("first@example.com", "First Academy"),
        unlocked_attempt("second@example.com", "Second Academy"),
    )

    assert outcomes == ["created", "created"], (
        "the unlocked race did not collide, so the locked test above is not "
        f"evidence of anything: {outcomes}"
    )
    assert await _owner_count(pg_sessions) == 2
