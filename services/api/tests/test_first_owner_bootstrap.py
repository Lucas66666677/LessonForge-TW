"""The first owner has to come from somewhere, and it could not.

Signing in needs a membership -- `login` looks the user up, then requires a
row joining them to an organization, and answers 403 「帳號不屬於任何可用組織」
when there is none. Creating an organization needs `UserDep`, so it can only be
called by someone already signed in. That is a closed loop, and
`scripts/seed.py` -- the only other writer -- refuses when `APP_ENV=production`
because it creates demo accounts with shared passwords the production validator
forbids. So a fresh production database had no reachable first step.

The first group below proves the loop rather than describing it: a user with a
password and no membership is created directly, and login still refuses. The
rest cover `scripts/bootstrap_owner.py`, which is the one step that was
missing.

## What the status mode is for

"Nothing seeded an account" and "no account exists" are different claims. The
first is provable here, from the guard in `seed.py`. The second is a fact about
a live database that no test and no amount of source reading can establish, so
the script reports it instead of asserting it -- and the checks below pin the
three states it distinguishes.

## What "no owner" does not mean

An earlier version of the status report said that zero owner memberships meant
nobody could sign in. Independent review caught it, and it was wrong: `login`
joins `Membership` on `user_id` with no filter on `role`, so a teacher signs in
exactly as an owner does. `test_a_teacher_membership_is_enough_to_sign_in`
proves that through the public route, which is what keeps the corrected wording
honest.

Everything runs against the test database the suite already uses. No network,
no production, no credential: passwords in this file are local fixtures typed
into a throwaway SQLite file.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select

from lessonforge.database import SessionLocal
from lessonforge.models import Membership, Organization, User
from lessonforge.schemas import Role
from lessonforge.security import hash_password, verify_password

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_SCRIPT = REPO_ROOT / "scripts" / "seed.py"


def _load_bootstrap():
    """Load the script by path: `scripts/` is not an importable package."""

    path = REPO_ROOT / "scripts" / "bootstrap_owner.py"
    spec = importlib.util.spec_from_file_location("_lessonforge_bootstrap_owner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = _load_bootstrap()

#: Local fixtures, never a real credential. Long enough to clear the minimum.
OWNER_PASSWORD = "local-test-owner-password"


@pytest_asyncio.fixture
async def db_session():
    """A session over the suite's test database.

    `conftest.clean_database` drops and recreates every table per test, so each
    case here genuinely starts with no accounts -- which is what makes "first
    owner" mean what it says.
    """

    async with SessionLocal() as session:
        yield session


# --------------------------------------------------------------------------- #
# The deadlock, proven
# --------------------------------------------------------------------------- #


async def test_a_user_without_a_membership_cannot_sign_in(client, db_session) -> None:
    """The half of the loop that source reading alone would leave as a claim.

    A user row with a valid password hash is not enough: login rejects it with
    403 because no organization is joined to it. So bootstrapping only a user
    would not have unblocked anything.
    """

    db_session.add(
        User(
            email="stranded@example.com",
            display_name="Stranded",
            password_hash=hash_password(OWNER_PASSWORD),
        )
    )
    await db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "stranded@example.com", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 403, response.text
    assert "組織" in response.json()["detail"]


def test_creating_an_organization_requires_being_signed_in(client) -> None:
    """The other half: the route that would grant a membership needs one."""

    response = client.post("/api/organizations", json={"name": "Bootstrap Academy"})
    assert response.status_code == 401


def test_the_seed_script_refuses_in_production() -> None:
    """Why the loop was never broken by the tooling that already existed.

    Read from the script rather than executed: running it is exactly what must
    not happen here.
    """

    source = SEED_SCRIPT.read_text(encoding="utf-8")
    assert 'app_env == "production"' in source
    assert "Skipping demo seed" in source


# --------------------------------------------------------------------------- #
# The bootstrap
# --------------------------------------------------------------------------- #


async def test_it_creates_a_user_an_organization_and_an_owner_membership(db_session) -> None:
    created = await bootstrap.create_first_owner(
        db_session,
        email="Owner@Example.COM",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    user = await db_session.scalar(select(User).where(User.id == created["user_id"]))
    organization = await db_session.scalar(
        select(Organization).where(Organization.id == created["organization_id"])
    )
    membership = await db_session.scalar(
        select(Membership).where(Membership.user_id == created["user_id"])
    )

    assert user is not None and organization is not None and membership is not None
    assert membership.role == Role.owner.value
    assert membership.organization_id == organization.id
    # Normalised, because login looks the address up lowercased.
    assert user.email == "owner@example.com"
    assert organization.slug == "bootstrap-academy"


async def test_the_bootstrapped_owner_can_actually_sign_in(client, db_session) -> None:
    """The check that makes this tooling rather than three inserts.

    Everything else asserts rows; this asserts the outcome those rows exist
    for, through the same public route a person would use.
    """

    await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["role"] == "owner"
    assert body["user"]["organization_name"] == "Bootstrap Academy"
    assert body["access_token"]


async def test_the_password_is_stored_only_as_a_hash(db_session) -> None:
    created = await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )
    user = await db_session.scalar(select(User).where(User.id == created["user_id"]))

    assert OWNER_PASSWORD not in user.password_hash
    assert user.password_hash.startswith("$argon2")
    assert verify_password(OWNER_PASSWORD, user.password_hash)


async def test_it_refuses_when_an_owner_already_exists(db_session) -> None:
    """A second owner must be a deliberate act through the audited route.

    Without this the script would be a way to add an owner to a live
    organization, quietly, with no audit entry.
    """

    await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    with pytest.raises(bootstrap.BootstrapError, match="already exists"):
        await bootstrap.create_first_owner(
            db_session,
            email="second@example.com",
            display_name="Second",
            organization_name="Another Academy",
            password=OWNER_PASSWORD,
            require_exclusive=False,
        )


async def test_it_refuses_an_email_that_already_has_a_user(db_session) -> None:
    """Re-running with the same address must not silently do nothing.

    A user with no membership is exactly the stranded state above; quietly
    treating that as success would leave the operator believing they had
    bootstrapped an owner who still cannot sign in.
    """

    db_session.add(
        User(
            email="taken@example.com",
            display_name="Taken",
            password_hash=hash_password(OWNER_PASSWORD),
        )
    )
    await db_session.commit()

    with pytest.raises(bootstrap.BootstrapError, match="already exists"):
        await bootstrap.create_first_owner(
            db_session,
            email="taken@example.com",
            display_name="Taken",
            organization_name="Bootstrap Academy",
            password=OWNER_PASSWORD,
            require_exclusive=False,
        )


# --------------------------------------------------------------------------- #
# It never invents a credential
# --------------------------------------------------------------------------- #


def test_it_refuses_to_run_without_a_password() -> None:
    """There is no default and nothing generated: the operator supplies it."""

    with pytest.raises(bootstrap.BootstrapError, match=bootstrap.PASSWORD_ENV_VAR):
        bootstrap.validate_password("")


@pytest.mark.parametrize("published", bootstrap.RETIRED_PASSWORDS)
def test_it_refuses_a_password_this_repository_published(published: str) -> None:
    """A retired credential must not return through a new door.

    `scripts/check_demo_credentials.py` keeps it out of shipped source; this
    keeps it out of the database.
    """

    with pytest.raises(bootstrap.BootstrapError, match="published"):
        bootstrap.validate_password(published)


def test_the_retired_list_comes_from_the_credential_checker() -> None:
    """One list, not two, and the bootstrap must not carry the values itself.

    The first version of this script hard-coded them -- and
    `scripts/check_demo_credentials.py` failed the build for it, because that
    checker refuses any file but itself containing a retired credential. Two
    copies of one incident also drift. So the list is read from the checker,
    and this pins both halves: it is non-empty, and the literal is not written
    into the bootstrap.
    """

    assert bootstrap.RETIRED_PASSWORDS, "the retired-credential list came back empty"

    source = (REPO_ROOT / "scripts" / "bootstrap_owner.py").read_text(encoding="utf-8")
    assert "check_demo_credentials.py" in source
    for published in bootstrap.RETIRED_PASSWORDS:
        assert published not in source, (
            f"{published!r} is written into the bootstrap; read it from the "
            f"checker instead, which is the only file allowed to contain it"
        )


def test_it_refuses_a_short_password() -> None:
    with pytest.raises(bootstrap.BootstrapError, match="characters"):
        bootstrap.validate_password("short")


def test_a_supplied_password_is_accepted() -> None:
    """Guards the guard: the refusals above are a filter, not a wall."""

    assert bootstrap.validate_password(OWNER_PASSWORD) is None


def test_it_refuses_rather_than_prompting_when_not_asked(monkeypatch) -> None:
    """The default path must never block, whatever stdin looks like.

    Prompting is opt-in because `getpass` does not reliably fail when nobody is
    watching: on some platforms it reads the console directly, so redirecting
    stdin does not stop it. Building this script, the first version hung until
    it was killed, with no output -- a bootstrap that can silently hang a
    deploy step is worse than one that refuses.
    """

    monkeypatch.delenv(bootstrap.PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr(
        bootstrap.getpass,
        "getpass",
        lambda *_args, **_kwargs: pytest.fail("the default path must not prompt"),
    )

    with pytest.raises(bootstrap.BootstrapError, match=bootstrap.PASSWORD_ENV_VAR):
        bootstrap.read_password(allow_prompt=False)


def test_it_refuses_to_prompt_where_nobody_can_answer(monkeypatch) -> None:
    """`--prompt` on a pipe is a hang waiting to happen, so it is refused."""

    monkeypatch.delenv(bootstrap.PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(
        bootstrap.getpass,
        "getpass",
        lambda *_args, **_kwargs: pytest.fail("must not prompt without a terminal"),
    )

    with pytest.raises(bootstrap.BootstrapError, match="not a terminal"):
        bootstrap.read_password(allow_prompt=True)


def test_the_environment_value_is_used_when_present(monkeypatch) -> None:
    """Guards the guards above: the refusals are a gate, not a wall."""

    monkeypatch.setenv(bootstrap.PASSWORD_ENV_VAR, OWNER_PASSWORD)
    assert bootstrap.read_password(allow_prompt=False) == OWNER_PASSWORD


def test_no_credential_is_written_into_the_script() -> None:
    """The script may name the variable; it may not carry a value.

    Read as source, because a default that only appears on one branch would not
    show up in any single execution path.
    """

    source = (REPO_ROOT / "scripts" / "bootstrap_owner.py").read_text(encoding="utf-8")
    assert 'os.environ.get(PASSWORD_ENV_VAR)' in source
    assert 'os.environ.get(PASSWORD_ENV_VAR, "' not in source
    assert "getpass" in source, "without a prompt the only input path is an env var"


# --------------------------------------------------------------------------- #
# Status: the three states it has to tell apart
# --------------------------------------------------------------------------- #


async def test_status_reports_an_empty_database(db_session) -> None:
    counts = await bootstrap.read_status(db_session)
    assert counts == {
        "users": 0,
        "organizations": 0,
        "memberships": 0,
        "active_memberships": 0,
        "owner_memberships": 0,
    }
    assert "no accounts" in bootstrap.describe_status(counts)


async def test_status_distinguishes_users_without_a_membership(db_session) -> None:
    """The state a naive check would call "an account exists" and stop.

    It does exist, and it cannot sign in -- but the reason is the missing
    *membership*, not the missing owner role. Those came apart under review:
    a teacher membership signs in perfectly well, so only a zero membership
    count supports the claim that nobody can get in.
    """

    db_session.add(
        User(
            email="stranded@example.com",
            display_name="Stranded",
            password_hash=hash_password(OWNER_PASSWORD),
        )
    )
    await db_session.commit()

    counts = await bootstrap.read_status(db_session)
    assert counts["users"] == 1
    assert counts["memberships"] == 0
    assert counts["owner_memberships"] == 0
    described = bootstrap.describe_status(counts)
    assert "none of them can sign in" in described


async def test_status_reports_an_existing_owner(db_session) -> None:
    await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    counts = await bootstrap.read_status(db_session)
    assert counts["owner_memberships"] == 1
    assert "already exists" in bootstrap.describe_status(counts)


async def test_status_reports_counts_and_no_account_content(db_session) -> None:
    """It answers "is there an owner", not "who is the owner".

    An operator may run this against production and paste the output into an
    issue; it must not carry an address or a hash.
    """

    await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    counts = await bootstrap.read_status(db_session)
    described = bootstrap.describe_status(counts)
    assert set(counts) == {
        "users",
        "organizations",
        "memberships",
        "active_memberships",
        "owner_memberships",
    }
    for leaked in ("owner@example.com", "First Owner", "Bootstrap Academy", OWNER_PASSWORD):
        assert leaked not in described


# --------------------------------------------------------------------------- #
# Zero owners is not zero sign-ins
# --------------------------------------------------------------------------- #


async def _seed_ownerless_organization(db_session):
    """An organization whose only member is a teacher. No owner anywhere."""

    organization = Organization(name="Existing Academy", slug="existing-academy")
    user = User(
        email="teacher@example.com",
        display_name="Teacher",
        password_hash=hash_password(OWNER_PASSWORD),
    )
    db_session.add_all([organization, user])
    await db_session.flush()
    db_session.add(
        Membership(organization_id=organization.id, user_id=user.id, role=Role.teacher.value)
    )
    await db_session.commit()
    return organization


async def test_a_teacher_membership_is_enough_to_sign_in(client, db_session) -> None:
    """The regression for the claim review rejected.

    `login` joins `Membership` on `user_id` and never looks at `role`, so the
    owner count says nothing about who can sign in. This proves it through the
    public route rather than by reading the query: a teacher, with no owner
    anywhere in the database, gets a token.
    """

    await _seed_ownerless_organization(db_session)

    response = client.post(
        "/api/auth/login",
        json={"email": "teacher@example.com", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == "teacher"

    counts = await bootstrap.read_status(db_session)
    assert counts["owner_memberships"] == 0
    assert counts["memberships"] == 1

    described = bootstrap.describe_status(counts)
    assert "CAN sign in" in described
    assert (
        "none of them can sign in" not in described
    ), "the report claimed nobody can sign in while a teacher just did"


async def test_status_separates_who_can_sign_in_from_who_owns(db_session) -> None:
    """The two counts answer two questions, and the report must not merge them.

    Reading only `owner_memberships` is what produced the wrong wording; the
    membership count is what actually answers "can anyone get in?".
    """

    await _seed_ownerless_organization(db_session)

    assert await bootstrap.read_status(db_session) == {
        "users": 1,
        "organizations": 1,
        "memberships": 1,
        "active_memberships": 1,
        "owner_memberships": 0,
    }


async def test_bootstrapping_beside_an_ownerless_organization_makes_a_separate_one(
    db_session,
) -> None:
    """What `--create` does in that state, checked rather than described.

    The status text says it creates a separate organization and leaves the
    existing one ownerless. That is a claim about behaviour, so it is pinned
    here: the first draft of that wording said the script would *refuse*, which
    it does not -- it only ever counts owners.
    """

    existing = await _seed_ownerless_organization(db_session)

    created = await bootstrap.create_first_owner(
        db_session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
        require_exclusive=False,
    )

    assert created["organization_id"] != existing.id
    still_ownerless = await db_session.scalar(
        select(Membership).where(
            Membership.organization_id == existing.id,
            Membership.role == Role.owner.value,
        )
    )
    assert still_ownerless is None


# --------------------------------------------------------------------------- #
# Two operators at once
# --------------------------------------------------------------------------- #


class _RecordingSession:
    """A stand-in that records the order of calls. Not a database.

    Every query answers "no rows", which is the state a first bootstrap runs
    in, and nothing is written anywhere. It exists for the one property a real
    session cannot show on SQLite: which statement is issued first.
    """

    def __init__(self, dialect: str) -> None:
        self._dialect = dialect
        self.calls: list[str] = []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name=self._dialect))

    async def execute(self, statement, params=None):
        self.calls.append(f"execute {statement} {params}")
        return None

    async def scalar(self, statement):
        self.calls.append(f"scalar {statement}")
        return None

    def add(self, instance) -> None:
        self.calls.append(f"add {type(instance).__name__}")

    async def flush(self) -> None:
        self.calls.append("flush")

    async def commit(self) -> None:
        self.calls.append("commit")


def _first_index(calls: list[str], needle: str) -> int:
    for index, call in enumerate(calls):
        if needle in call:
            return index
    raise AssertionError(f"{needle!r} never appeared in {calls!r}")


async def test_it_takes_a_transaction_scoped_advisory_lock_on_postgresql() -> None:
    """`_xact_` is the part that matters.

    A session-scoped lock would outlive the transaction, so a crashed run could
    leave it held and block every later bootstrap until the connection died.
    """

    session = _RecordingSession("postgresql")
    assert await bootstrap.hold_bootstrap_lock(session) is True

    assert len(session.calls) == 1
    (statement,) = session.calls
    assert "pg_advisory_xact_lock" in statement
    assert str(bootstrap.BOOTSTRAP_LOCK_KEY) in statement


async def test_the_lock_is_taken_before_the_owner_count_is_read() -> None:
    """The ordering is the whole guard.

    Counting first and locking second reads as equally safe and is not: both
    runs would already hold the answer "zero owners" before either one waited.
    """

    session = _RecordingSession("postgresql")
    await bootstrap.create_first_owner(
        session,
        email="owner@example.com",
        display_name="First Owner",
        organization_name="Bootstrap Academy",
        password=OWNER_PASSWORD,
    )

    lock = _first_index(session.calls, "pg_advisory_xact_lock")
    count = _first_index(session.calls, "count(*)")
    write = _first_index(session.calls, "add ")
    assert lock < count < write, session.calls


async def test_it_fails_closed_where_it_cannot_serialise() -> None:
    """Proceeding silently would be a race; a comment claiming protection that
    is not there is worse than a refusal that says so."""

    session = _RecordingSession("sqlite")
    with pytest.raises(bootstrap.BootstrapError, match="PostgreSQL"):
        await bootstrap.hold_bootstrap_lock(session)
    assert session.calls == [], "it must refuse before touching the database"


async def test_the_opt_out_is_explicit_and_reports_that_no_lock_is_held() -> None:
    """Guards the guard above, and pins the return value.

    Returning True here would let a caller believe a lock exists when none
    does, which is the failure this whole path removes.
    """

    session = _RecordingSession("sqlite")
    assert await bootstrap.hold_bootstrap_lock(session, require_exclusive=False) is False
    assert session.calls == []


async def test_create_refuses_before_writing_anything_on_an_unserialisable_database(
    db_session,
) -> None:
    """The refusal is the default, and it lands before the first row."""

    with pytest.raises(bootstrap.BootstrapError, match="PostgreSQL"):
        await bootstrap.create_first_owner(
            db_session,
            email="owner@example.com",
            display_name="First Owner",
            organization_name="Bootstrap Academy",
            password=OWNER_PASSWORD,
        )

    assert await bootstrap.read_status(db_session) == {
        "users": 0,
        "organizations": 0,
        "memberships": 0,
        "active_memberships": 0,
        "owner_memberships": 0,
    }


def test_the_lock_key_is_reproducible_from_its_namespace() -> None:
    """A per-process value would hand two concurrent runs two different locks.

    That is why the key is a blake2b digest of a fixed name rather than
    `hash()`, whose randomisation would defeat the guard silently: every run
    would take a lock, and no run would ever wait.
    """

    expected = int.from_bytes(
        hashlib.blake2b(b"lessonforge.bootstrap_owner.first_owner", digest_size=8).digest(),
        "big",
        signed=True,
    )
    assert bootstrap.BOOTSTRAP_LOCK_KEY == expected
    assert -(2**63) <= bootstrap.BOOTSTRAP_LOCK_KEY < 2**63, "pg takes a signed bigint"

    # Parsed, not grepped: the first version of this check matched the comment
    # that explains why `hash()` is not used, and failed on prose.
    tree = ast.parse((REPO_ROOT / "scripts" / "bootstrap_owner.py").read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "hash" not in called, "randomised per process; use blake2b"


def test_the_safe_path_is_the_default_and_the_opt_out_is_reachable() -> None:
    """A guard nobody can turn off gets deleted; one that is off by default is
    not a guard. Both halves are pinned."""

    source = (REPO_ROOT / "scripts" / "bootstrap_owner.py").read_text(encoding="utf-8")
    assert "--allow-unsynchronized" in source
    assert "require_exclusive=not args.allow_unsynchronized" in source

    assert inspect.signature(bootstrap.create_first_owner).parameters[
        "require_exclusive"
    ].default is True
    assert inspect.signature(bootstrap.hold_bootstrap_lock).parameters[
        "require_exclusive"
    ].default is True


async def test_a_deactivated_member_cannot_sign_in_and_is_not_reported_as_able_to(
    client, db_session
) -> None:
    """The same overclaim, one step smaller, and it must not ship either.

    `login` checks `is_active` and answers 401 before it ever looks for a
    membership, so a membership held by a deactivated user lets nobody in.
    Counting plain memberships and calling that "people CAN sign in" would be
    exactly the error under review, in miniature.
    """

    organization = Organization(name="Existing Academy", slug="existing-academy")
    user = User(
        email="retired@example.com",
        display_name="Retired",
        password_hash=hash_password(OWNER_PASSWORD),
        is_active=False,
    )
    db_session.add_all([organization, user])
    await db_session.flush()
    db_session.add(
        Membership(organization_id=organization.id, user_id=user.id, role=Role.teacher.value)
    )
    await db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "retired@example.com", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 401, response.text

    counts = await bootstrap.read_status(db_session)
    assert counts["memberships"] == 1
    assert counts["active_memberships"] == 0

    described = bootstrap.describe_status(counts)
    assert "deactivated" in described
    assert "CAN sign in" not in described, (
        "the report claimed people can sign in while login just refused the only member"
    )


async def test_an_active_membership_is_what_the_report_calls_a_sign_in(
    client, db_session
) -> None:
    """Guards the guard above: the deactivated branch must not swallow the
    ordinary case, where a member really can sign in."""

    await _seed_ownerless_organization(db_session)

    counts = await bootstrap.read_status(db_session)
    assert counts["memberships"] == counts["active_memberships"] == 1
    described = bootstrap.describe_status(counts)
    assert "CAN sign in" in described
    assert "deactivated" not in described
