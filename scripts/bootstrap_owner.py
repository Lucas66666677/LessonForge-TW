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
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from sqlalchemy import func, select  # noqa: E402

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
    """Counts only. No email, display name or password hash is read."""
    users = await session.scalar(select(func.count()).select_from(User))
    organizations = await session.scalar(select(func.count()).select_from(Organization))
    owners = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.role == Role.owner.value)
    )
    return {
        "users": int(users or 0),
        "organizations": int(organizations or 0),
        "owner_memberships": int(owners or 0),
    }


def describe_status(counts: dict[str, int]) -> str:
    lines = [
        f"users:             {counts['users']}",
        f"organizations:     {counts['organizations']}",
        f"owner memberships: {counts['owner_memberships']}",
        "",
    ]
    if counts["owner_memberships"]:
        lines.append("An owner already exists. --create would refuse; nothing to bootstrap.")
    elif counts["users"]:
        lines.append(
            "Users exist but none owns an organization, so none of them can sign in: "
            "login requires a membership. --create will add an owner."
        )
    else:
        lines.append("The database holds no accounts. --create will create the first owner.")
    return "\n".join(lines)


async def create_first_owner(
    session, *, email: str, display_name: str, organization_name: str, password: str
) -> dict[str, str]:
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
