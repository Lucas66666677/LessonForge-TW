"""Deactivate the seeded Demo accounts on a running deployment.

Why this exists: the publicly displayed Demo credentials
(`owner@demo.lessonforge.tw` / `teacher@demo.lessonforge.tw` and a password that
was printed on the public preview page) were seeded into the live database
before the current guards existed. Removing them from the source and rebuilding
the frontend stops *advertising* them; it does not stop them *working*.
`scripts/seed.py`'s `ensure_user` only ever creates a user that is missing --
it never rewrites an existing `password_hash` -- so the old hash is still
whatever it was.

`is_active` is enforced on both entry points (`lessonforge/api.py`'s login and
`lessonforge/dependencies.py`'s session lookup both require it to be true), so
setting it false is a complete and reversible kill switch. That is preferable
to rotating the password: it leaves the demo data intact for reference and can
be undone with `--reactivate` if the accounts are ever wanted back behind a
private password.

Usage -- dry run first, which is the default and writes nothing:

    DATABASE_URL="postgresql://..." python scripts/disable_demo_accounts.py
    DATABASE_URL="postgresql://..." python scripts/disable_demo_accounts.py --apply

Targets `DEMO_OWNER_EMAIL` and `DEMO_TEACHER_EMAIL` (the same settings
`seed.py` uses) unless `--email` is given, which may be repeated.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

from sqlalchemy import func, select  # noqa: E402

from lessonforge.config import get_settings  # noqa: E402
from lessonforge.database import SessionLocal  # noqa: E402
from lessonforge.models import User  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write. Without it the script only reports what it would change.",
    )
    parser.add_argument(
        "--reactivate",
        action="store_true",
        help="set is_active back to true instead of false.",
    )
    parser.add_argument(
        "--email",
        action="append",
        default=None,
        help="override the target addresses; repeatable.",
    )
    return parser.parse_args(argv)


def target_emails(override: list[str] | None) -> list[str]:
    if override:
        return override
    settings = get_settings()
    return [settings.demo_owner_email, settings.demo_teacher_email]


async def run(args: argparse.Namespace) -> int:
    desired_active = bool(args.reactivate)
    emails = target_emails(args.email)
    changed = 0

    async with SessionLocal() as session:
        for email in emails:
            user = await session.scalar(
                select(User).where(func.lower(User.email) == email.lower())
            )
            if user is None:
                print(f"  {email}: not present -- nothing to do")
                continue
            if user.is_active == desired_active:
                print(f"  {email}: already is_active={desired_active}")
                continue
            print(f"  {email}: is_active {user.is_active} -> {desired_active}")
            changed += 1
            if args.apply:
                user.is_active = desired_active
        if args.apply and changed:
            await session.commit()

    if not args.apply:
        print(f"\nDry run: {changed} row(s) would change. Re-run with --apply to write.")
        return 0

    print(f"\nDone: {changed} row(s) updated.")
    if changed and not desired_active:
        print(
            "Verify from outside: a login attempt with the old Demo credentials must "
            "now be rejected."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
