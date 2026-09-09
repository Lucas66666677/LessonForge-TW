"""Create the first owner, or report whether one already exists.

## The deadlock this exists to break

Every later step of the product is reachable only from an owner account, and
nothing could create the first one in production. The three ways in are all
closed:

* ``POST /auth/login`` finds the user, then requires a membership -- with none
  it answers ``403 帳號不屬於任何可用組織``. A user row alone cannot sign in.
* ``POST /organizations`` creates the organization *and* the owner membership,
  but takes ``UserDep``: you must already be signed in to call it.
* ``POST /organizations/current/members`` creates further users, and needs an
  owner or admin to exist already.

The entry condition is therefore circular: signing in needs a membership, and
getting a membership needs signing in. ``scripts/seed.py`` is the only other
writer, and it refuses when ``APP_ENV=production`` -- correctly, because it
creates demo accounts with shared passwords that
``Settings.validate_production_sign_in`` forbids. This script is the missing
step, and only that step: one user, one organization, one owner membership.

## Two modes, and the difference between them is the point

    python scripts/bootstrap_owner.py --status
    python scripts/bootstrap_owner.py --create --email you@example.com --organization "Your Academy"

``--status`` is read-only. Knowing that *nothing seeded an account* is not the
same as knowing that *no account exists*. The first is a fact about this
repository, provable by reading the guard in ``seed.py``. The second is a fact
about a live database, which no amount of source reading can settle: an
operator may have inserted rows by hand, and an earlier build may have seeded
before that guard existed. ``--status`` is how the second question gets
answered instead of assumed.

``--create`` refuses when any owner membership already exists, so it cannot
quietly mint a second owner beside one that was provisioned another way.

## Two operators at once

``--create`` checks that no owner exists and then writes three rows. Between
those two steps a second run can make the same check, get the same answer, and
also write -- two owners of two organizations, from a command whose entire
contract is that it creates the first one. On PostgreSQL that window is closed
with ``pg_advisory_xact_lock``, held for the transaction that spans the check
and the writes: the second run waits, then sees the owner the first one created
and refuses. It needs no table and no migration.

Nothing equivalent is guaranteed on other dialects, so there this script refuses
rather than pretending. ``--allow-unsynchronized`` is the deliberate opt-out for
an operator who knows they are the only writer.

## What it will not do

It never invents a credential. The password comes from
``BOOTSTRAP_OWNER_PASSWORD`` or a prompt; there is no default, no generated
value, and it is never printed or logged. It refuses any password this
repository has published, so a retired demo credential cannot return through a
new door. It runs no migration and writes nothing beyond those three rows.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import hashlib
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from sqlalchemy import func, select, text  # noqa: E402

from lessonforge.config import get_settings  # noqa: E402
from lessonforge.database import SessionLocal  # noqa: E402
from lessonforge.models import Membership, Organization, User  # noqa: E402
from lessonforge.schemas import Role  # noqa: E402
from lessonforge.security import hash_password  # noqa: E402

#: The variable the operator supplies the password through. There is
#: deliberately no default: a bootstrap that runs unattended with a value this
#: file knows is a bootstrap that ships a credential.
PASSWORD_ENV_VAR = "BOOTSTRAP_OWNER_PASSWORD"

def _retired_passwords() -> tuple[str, ...]:
    """Credentials this repository has published, read from the one list.

    Not copied here. ``scripts/check_demo_credentials.py`` already owns that
    list, and it refuses any *other* file that contains one of the values --
    which is how the first version of this script was caught duplicating it.
    Loading the checker means the two cannot drift, and it keeps the literal in
    the single file that is exempt from its own rule.
    """

    checker = Path(__file__).resolve().parent / "check_demo_credentials.py"
    spec = importlib.util.spec_from_file_location("_lessonforge_credential_checker", checker)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.RETIRED_SECRETS)


#: Resolved once at import; the checker is a repository file, not configuration.
RETIRED_PASSWORDS = _retired_passwords()

#: Long enough that a hand-typed value is deliberate. Not a policy engine: this
#: refuses something obviously disposable, it does not score entropy.
MINIMUM_PASSWORD_LENGTH = 12


class BootstrapError(RuntimeError):
    """A refusal the operator has to act on, not a traceback to decode."""


#: Namespace for the PostgreSQL advisory lock. Derived rather than picked so the
#: number is reproducible from a name, and hashed with blake2b rather than
#: `hash()`, which is randomised per process and would hand two concurrent runs
#: two different locks -- the exact failure this is meant to prevent.
BOOTSTRAP_LOCK_NAMESPACE = "lessonforge.bootstrap_owner.first_owner"

#: `pg_advisory_xact_lock` takes a signed 64-bit key, so the digest is read as one.
BOOTSTRAP_LOCK_KEY = int.from_bytes(
    hashlib.blake2b(BOOTSTRAP_LOCK_NAMESPACE.encode("utf-8"), digest_size=8).digest(),
    "big",
    signed=True,
)


async def hold_bootstrap_lock(session, *, require_exclusive: bool = True) -> bool:
    """Serialise this run against another one, or refuse to guess.

    Returns True only when a lock is genuinely held for the remainder of the
    transaction -- never as a way of reporting that none was needed.

    The lock is transaction-scoped, so it covers the whole check-then-write and
    is released by the commit. That is why no table and no migration are
    involved, and why it cannot be left behind by a crashed run.

    On any other dialect there is no equivalent to reach for, and the honest
    answer is a refusal rather than a comment claiming protection that is not
    there. SQLite is the suite's database, so the tests pass
    ``require_exclusive=False`` explicitly: opting out is visible at the call
    site instead of being the default everywhere.
    """

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": BOOTSTRAP_LOCK_KEY}
        )
        return True
    if require_exclusive:
        raise BootstrapError(
            f"Refusing to bootstrap on a {dialect!r} database. Only one owner may "
            f"ever be created this way, and only PostgreSQL offers a lock that can "
            f"hold across the check and the writes; here two simultaneous runs "
            f"would both read zero owners and both succeed. Run this against the "
            f"PostgreSQL deployment, or pass --allow-unsynchronized if you are "
            f"certain nothing else is writing."
        )
    return False


def slugify(name: str) -> str:
    """A URL-safe slug, in the shape ``POST /organizations`` would produce."""
    cleaned = "".join(character if character.isalnum() else "-" for character in name.lower())
    collapsed = "-".join(part for part in cleaned.split("-") if part)
    return collapsed or "organization"


def validate_password(password: str) -> None:
    if not password:
        raise BootstrapError(
            f"No password supplied. Set {PASSWORD_ENV_VAR} or answer the prompt; "
            f"this script will not invent one."
        )
    if password in RETIRED_PASSWORDS:
        raise BootstrapError(
            "That password was published in this repository and retired. Choose one "
            "that has never been committed anywhere."
        )
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise BootstrapError(
            f"The owner password must be at least {MINIMUM_PASSWORD_LENGTH} characters."
        )


def read_password(*, allow_prompt: bool) -> str:
    """The password, from the environment or -- only if asked -- a prompt.

    Prompting is opt-in rather than a fallback. Operators run this in a
    container shell or a one-off deploy job, and `getpass` there does not
    reliably fail when nobody is watching: on some platforms it reads the
    console directly, so redirecting stdin does not stop it. Measured while
    building this: with stdin redirected from /dev/null it hung until killed,
    with no output at all. A bootstrap that can hang a deploy step silently is
    worse than one that refuses, so the default path never blocks.

    `--prompt` is for an operator at a real terminal who would rather not put a
    password in their shell history. It also checks `isatty`, which catches the
    non-interactive case on the platforms where that is honest.
    """

    supplied = os.environ.get(PASSWORD_ENV_VAR)
    if supplied:
        return supplied
    if not allow_prompt:
        raise BootstrapError(
            f"No {PASSWORD_ENV_VAR} set. Supply it for this one command, or pass "
            f"--prompt to be asked at a terminal. This script will not invent one."
        )
    if not sys.stdin.isatty():
        raise BootstrapError(
            "--prompt was given but stdin is not a terminal, so there is nobody "
            f"to ask. Set {PASSWORD_ENV_VAR} instead."
        )
    return getpass.getpass("Owner password (not echoed, not stored): ")


async def read_status(session) -> dict[str, int]:
    """Counts only. No email, display name or password hash is read.

    `memberships` is counted apart from `owner_memberships` because they answer
    different questions, and conflating them is the mistake this report used to
    make: sign-in requires *a* membership, of any role.
    """
    users = await session.scalar(select(func.count()).select_from(User))
    organizations = await session.scalar(select(func.count()).select_from(Organization))
    memberships = await session.scalar(select(func.count()).select_from(Membership))
    owners = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.role == Role.owner.value)
    )
    return {
        "users": int(users or 0),
        "organizations": int(organizations or 0),
        "memberships": int(memberships or 0),
        "owner_memberships": int(owners or 0),
    }


def describe_status(counts: dict[str, int]) -> str:
    """What the counts do, and do not, establish.

    An earlier version said that zero owner memberships meant nobody could sign
    in. That was wrong, and independent review caught it. `POST /auth/login`
    joins `Membership` on `user_id` with **no role filter**, so a teacher or an
    admin signs in exactly as an owner does -- `test_first_owner_bootstrap.py`
    now proves that by logging in with a teacher membership.

    Zero owners is a fact about the `owner` role and nothing more. It does not
    even mean nobody can add members: the only role-gated route,
    `POST /organizations/current/members`, accepts owner *or* admin. The
    question "can anyone sign in?" is answered by `memberships`, which is why
    both are counted and reported.
    """
    lines = [
        f"users:             {counts['users']}",
        f"organizations:     {counts['organizations']}",
        f"memberships:       {counts['memberships']}",
        f"owner memberships: {counts['owner_memberships']}",
        "",
    ]
    if counts["owner_memberships"]:
        lines.append(
            "An owner already exists, so this deployment is past bootstrap. "
            "--create will refuse."
        )
    elif counts["memberships"]:
        lines.append(
            "No account holds the owner role, but memberships exist, so people "
            "CAN sign in: login accepts a membership of any role. An admin, if "
            "there is one, can already add members. --create still runs here -- "
            "it refuses only when an owner exists -- but it creates a SEPARATE "
            "organization and owns only that one; the existing organizations stay "
            "ownerless."
        )
    elif counts["users"]:
        lines.append(
            "Users exist and none has a membership, so none of them can sign in: "
            "login requires one. --create will create the first owner."
        )
    else:
        lines.append("The database holds no accounts. --create will create the first owner.")
    return "\n".join(lines)


async def create_first_owner(
    session,
    *,
    email: str,
    display_name: str,
    organization_name: str,
    password: str,
    require_exclusive: bool = True,
) -> dict[str, str]:
    """Create the one first owner, and nothing if one is already there.

    The lock is taken *before* the count is read. The other order looks
    equivalent and is not: reading first and locking afterwards leaves open
    precisely the window the lock exists to close, because both runs would have
    already read zero. ``test_the_lock_is_taken_before_the_owner_count_is_read``
    pins the ordering rather than trusting this paragraph.
    """

    await hold_bootstrap_lock(session, require_exclusive=require_exclusive)

    existing_owner = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.role == Role.owner.value)
    )
    if existing_owner:
        raise BootstrapError(
            "An owner membership already exists. This script bootstraps only the first "
            "one; add further accounts through POST /organizations/current/members, "
            "which records an audit entry."
        )

    normalized = email.strip().lower()
    if not normalized:
        raise BootstrapError("An owner email is required.")
    duplicate = await session.scalar(select(User).where(func.lower(User.email) == normalized))
    if duplicate is not None:
        raise BootstrapError(
            "A user with that email already exists but owns nothing. Re-run with a "
            "different address, or grant that user an owner membership deliberately."
        )

    organization = Organization(name=organization_name, slug=slugify(organization_name))
    session.add(organization)
    await session.flush()

    user = User(
        email=normalized,
        display_name=display_name,
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()

    session.add(Membership(organization_id=organization.id, user_id=user.id, role=Role.owner.value))
    await session.commit()
    return {
        "user_id": user.id,
        "organization_id": organization.id,
        "organization_slug": organization.slug,
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap or inspect the first owner account.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="report account counts, change nothing")
    mode.add_argument("--create", action="store_true", help="create the first owner")
    parser.add_argument("--email", help="the owner's email address")
    parser.add_argument("--display-name", default="", help="shown in the members list")
    parser.add_argument("--organization", help="the organization's display name")
    parser.add_argument(
        "--prompt",
        action="store_true",
        help="ask for the password at a terminal instead of reading the environment",
    )
    parser.add_argument(
        "--allow-unsynchronized",
        action="store_true",
        help=(
            "proceed on a database where two simultaneous runs cannot be serialised; "
            "only when you are certain nothing else is writing"
        ),
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    async with SessionLocal() as session:
        if args.status:
            print(f"APP_ENV={settings.app_env}")
            print(describe_status(await read_status(session)))
            return 0

        if not args.email or not args.organization:
            raise BootstrapError("--create requires --email and --organization.")
        password = read_password(allow_prompt=args.prompt)
        validate_password(password)
        created = await create_first_owner(
            session,
            email=args.email,
            display_name=args.display_name or args.email.split("@")[0],
            organization_name=args.organization,
            password=password,
            require_exclusive=not args.allow_unsynchronized,
        )

    print("First owner created.")
    print(f"  organization: {created['organization_slug']} ({created['organization_id']})")
    print(f"  user:         {created['user_id']}")
    print("The password was not stored or printed. Sign in at the public site to verify.")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    try:
        raise SystemExit(asyncio.run(main()))
    except BootstrapError as error:
        print(f"Refused: {error}", file=sys.stderr)
        raise SystemExit(2) from None
