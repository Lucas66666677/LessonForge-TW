"""The commit this process was built from, validated before it is published.

`/health` already carries a `version` field, and that is precisely the problem
it does not solve: `__version__` is the package string `"0.1.0"`, hard-coded in
`lessonforge/__init__.py`. It is the same on every release, so it answers the
question "which build is running?" with something that looks like an answer and
is not -- which is worse than answering nothing, because an operator comparing
two probes sees agreement and concludes the deploy landed.

That field stays exactly as it is. Render polls `/health` as its deploy gate
(`render.yaml` `healthCheckPath`), `test_deploy_contract.py` drives the route
through that path, and a payload something already gates on is not a payload to
edit for convenience. The deployed commit gets its own route instead.

Render sets `RENDER_GIT_COMMIT` on every deploy, at build time and at runtime.
This module reads that one variable and nothing else in the environment.

Deliberately not a `Settings` field. `Settings` is deployment configuration,
loaded from the environment *and* from `.env`, cached by `lru_cache`, and
guarded by a production validator that refuses to boot. A commit SHA is none of
those things: it is platform metadata, it must never be settable from a
committed file, and it must never be able to stop a container starting. Reading
it here, per call, keeps all three true.

The route that serves this is unauthenticated, like `/health`. That makes the
parse below a **whitelist**: a value is published only when it already is a
commit SHA, normalized rather than echoed as typed. Whatever ends up in that
variable -- a database URL, a JWT secret, a whole `.env` line pasted into the
wrong dashboard box -- the only characters this module can emit are hexadecimal
digits.

A rejected value is not logged either. The reason to refuse it is that it might
be a secret, so writing it to the log would move the leak rather than close it.
"""

from __future__ import annotations

import os
import re

#: Render sets this on every deploy. It is the only variable this module reads.
REVISION_ENV_VAR = "RENDER_GIT_COMMIT"

#: A commit SHA, and nothing that is not one. The lower bound is git's own
#: abbreviation floor, so a short SHA set by hand on a host that is not Render
#: stays usable; the upper bound is a full SHA-1. Anchored at both ends, because
#: an unanchored pattern would find a SHA inside a longer string and publish a
#: value the platform never set -- the same "looks like an answer" failure the
#: static `version` field already demonstrates.
_COMMIT_SHA = re.compile(r"\A[0-9a-fA-F]{7,40}\Z")


def commit_sha_or_none(value: str | None) -> str | None:
    """Return `value` as a normalized commit SHA, or ``None`` if it is not one.

    Pure, and separate from the environment read below, so what may be published
    can be tested against inputs a process environment is awkward to hold.
    """
    if value is None:
        return None

    candidate = value.strip()
    if not _COMMIT_SHA.match(candidate):
        return None

    return candidate.lower()


def deployed_revision() -> str | None:
    """Return the commit this process was built from, or ``None`` if unknown.

    ``None`` covers two situations and deliberately does not tell them apart to
    the caller: the variable is unset -- every local run and every host that is
    not Render -- or it holds something that is not a commit SHA. Reporting
    which would mean reporting something about a value that may be a secret.
    """
    return commit_sha_or_none(os.getenv(REVISION_ENV_VAR))
