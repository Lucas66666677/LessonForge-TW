"""`/health` says which *package version* is running; nothing said which build.

`__version__` is `"0.1.0"`, hard-coded in `lessonforge/__init__.py`, and
`/health` publishes it as `version`. It is the same string on every release, so
it answers "which build is deployed?" with something shaped like an answer --
worse than answering nothing, because an operator comparing two probes across a
release sees agreement and concludes the deploy landed.

`GET /version` answers it properly, from `RENDER_GIT_COMMIT`, and `/health` is
left exactly as it was: Render gates every deploy on it (`render.yaml`
`healthCheckPath`, driven through by `test_deploy_contract.py`), so its payload
is a contract something already polls. The first group below pins that payload
byte for byte -- the serialized bytes, not just the parsed dict, since that is
what a gate and a human `curl` both actually see.

Two further properties are worth stating as tests, because neither is visible
in the handler:

1. **Only hexadecimal can be published.** The route is unauthenticated, and an
   environment variable's failure mode is holding the wrong thing -- a database
   URL, a JWT secret, a pasted `.env` line. A presence or length check would
   return every one of those to an anonymous caller. That is not hypothetical
   here: `PUBLIC_JWT_SECRETS` exists because this repository already shipped a
   length-only check that every published placeholder passed.

2. **The probe cannot be rate-limited into silence.** `/health` is exempt from
   the limiter because a gate that starts getting 429 is a gate that fails a
   healthy deploy. A revision probe polled during a rollout has the same
   problem, so it is exempt too, and that is asserted rather than assumed.

No network request is made and no credential appears in any assertion.
"""

from __future__ import annotations

import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from lessonforge import __version__
from lessonforge.config import get_settings
from lessonforge.main import app
from lessonforge.revision import (
    REVISION_ENV_VAR,
    commit_sha_or_none,
    deployed_revision,
)

VERSION_ROUTE = "/version"
HEALTH_ROUTE = "/health"

#: A real 40-character SHA-1, in the shape Render injects.
A_COMMIT_SHA = "33539b0c7a1e4d82f6b95c0e3a7d418be2f0c95d"

#: Exactly what `/health` has always returned, written out rather than rebuilt
#: from the handler's own expression: a test that recomputes the payload the
#: same way the handler does cannot notice the handler changing.
HEALTH_BODY = b'{"status":"ok","service":"lessonforge-api","version":"0.1.0"}'

#: What an environment variable holds when someone fills in the wrong dashboard
#: box. Every one is truthy, so a presence check would publish all of them, and
#: the JWT placeholders are the repository's own -- the exact values
#: `PUBLIC_JWT_SECRETS` exists to keep out of production.
NOT_A_COMMIT_SHA = [
    "postgresql+asyncpg://lessonforge:hunter2@db.internal.example:5432/lessonforge",
    "local-demo-secret-change-before-production-32-chars",
    "change-this-to-at-least-32-random-characters",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.9f7Qn0",
    "RENDER_GIT_COMMIT=33539b0",
    "https://lessonforge-tw-api-lucas.onrender.com",
    "refs/heads/main",
    "main",
    "0.1.0",
    "unknown",
    "$RENDER_GIT_COMMIT",
    "",
    "   ",
]


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _route(path: str) -> APIRoute | None:
    return next(
        (
            route
            for route in app.routes
            if isinstance(route, APIRoute) and route.path == path
        ),
        None,
    )


# --------------------------------------------------------------------------- #
# `/health` is untouched
# --------------------------------------------------------------------------- #


def test_the_health_payload_is_byte_for_byte_what_it_was(client: TestClient) -> None:
    """Render's deploy gate polls this, and a human reads it with `curl`.

    Pinned as bytes rather than as a parsed dict: key order and separators are
    part of what a reader compares between two deployments, and a dict
    comparison would pass while the wire format changed.
    """

    response = client.get(HEALTH_ROUTE)

    assert response.status_code == 200
    assert response.content == HEALTH_BODY


def test_the_static_version_field_is_still_the_package_string(
    client: TestClient,
) -> None:
    """Deliberately kept, deliberately useless for this purpose.

    Removing it would be a payload change to a gated route; the honest fix is a
    second route, which is what this file is about. Stating it here means the
    two facts stay visible together -- the field exists, and it is not a build
    identifier.
    """

    assert client.get(HEALTH_ROUTE).json()["version"] == __version__
    assert __version__ == "0.1.0"


def test_the_health_route_does_not_report_the_revision(client: TestClient) -> None:
    """The whole point of a separate route, stated as a failure condition.

    Adding the commit to `/health` would look like an improvement in review and
    would change a payload Render gates on.
    """

    assert set(client.get(HEALTH_ROUTE).json()) == {"status", "service", "version"}


# --------------------------------------------------------------------------- #
# What `/version` answers
# --------------------------------------------------------------------------- #


def test_it_reports_the_commit_the_platform_injected(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point, over real HTTP rather than by calling the handler."""

    monkeypatch.setenv(REVISION_ENV_VAR, A_COMMIT_SHA)
    response = client.get(VERSION_ROUTE)

    assert response.status_code == 200
    assert response.json() == {"revision": A_COMMIT_SHA}


def test_it_reports_null_when_the_platform_injected_nothing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every local run, and every host that is not Render, is in this state.

    `null` rather than a 500 or an invented string: an unknown revision is
    normal, and the route still has to answer.
    """

    monkeypatch.delenv(REVISION_ENV_VAR, raising=False)
    response = client.get(VERSION_ROUTE)

    assert response.status_code == 200
    assert response.json() == {"revision": None}


def test_the_payload_carries_the_revision_and_no_other_field(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A route answering "what is deployed?" invites more fields.

    `app_env`, the provider name, the model: all configuration, all on an
    unauthenticated route. Pinning the key set is what stops the next
    useful-sounding addition from being published to anyone who asks.
    """

    monkeypatch.setenv(REVISION_ENV_VAR, A_COMMIT_SHA)
    assert set(client.get(VERSION_ROUTE).json()) == {"revision"}


def test_the_route_consults_nothing(client: TestClient) -> None:
    """It reports the build, so it must answer when a dependency is down.

    `Depends(get_session)` in the signature is what would put the database in
    front of the one route whose job is to be answerable during exactly the
    incident that prompts the question. `test_deploy_contract.py` makes the
    same argument for `/health`.
    """

    route = _route(VERSION_ROUTE)
    assert route is not None, f"{VERSION_ROUTE} is no longer mounted"
    assert "GET" in route.methods
    injected = [dependency.name for dependency in route.dependant.dependencies]
    assert injected == [], f"{VERSION_ROUTE} now injects {injected}"


def test_the_revision_probe_is_exempt_from_the_rate_limiter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe that starts answering 429 mid-rollout cannot be trusted.

    `/health` is exempt for that reason and `/version` is polled the same way --
    repeatedly, while a deploy is in flight. Driven by actually exceeding the
    limit rather than by reading the exemption set, so the assertion is about
    behaviour and not about a literal.
    """

    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 1, raising=False)
    for _ in range(4):
        response = client.get(VERSION_ROUTE)
        assert response.status_code == 200, "the revision probe was rate-limited"


# --------------------------------------------------------------------------- #
# What may be published
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", NOT_A_COMMIT_SHA)
def test_a_value_that_is_not_a_commit_sha_is_never_published(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """The leak guard, driven through the route rather than the parser.

    Each of these is truthy, so a presence check would hand every one to an
    anonymous caller -- including two secrets this repository already knows are
    dangerous enough to keep a dedicated list of.
    """

    monkeypatch.setenv(REVISION_ENV_VAR, value)
    assert client.get(VERSION_ROUTE).json() == {"revision": None}


def test_the_parser_accepts_a_real_sha() -> None:
    """Guards the guard: prove the rejections above are a filter, not a wall.

    Without this, `commit_sha_or_none` could return `None` for every input and
    satisfy every rejection check in this file.
    """

    assert commit_sha_or_none(A_COMMIT_SHA) == A_COMMIT_SHA


def test_the_parser_normalizes_case_and_surrounding_whitespace() -> None:
    """A pasted value arrives with a newline; some tools print SHAs uppercase.

    Both name the same commit, so both stay usable -- but one published form
    means two probes of one deployment cannot disagree.
    """

    assert commit_sha_or_none(f"  {A_COMMIT_SHA.upper()}\n") == A_COMMIT_SHA


@pytest.mark.parametrize(
    "value",
    [
        A_COMMIT_SHA[:6],
        A_COMMIT_SHA + "0",
        A_COMMIT_SHA[:-1] + "g",
        A_COMMIT_SHA[:20] + " " + A_COMMIT_SHA[21:],
    ],
    ids=["too-short", "too-long", "non-hex-character", "embedded-space"],
)
def test_the_parser_rejects_near_misses(value: str) -> None:
    """Anchored, not searched: a SHA inside a longer string is not a SHA.

    `A_COMMIT_SHA + "0"` is the case that matters -- an unanchored pattern
    matches the leading 40 characters and publishes a value the platform never
    set. That is the same class of mistake as the static `version` field: a
    confident answer that is wrong.
    """

    assert commit_sha_or_none(value) is None


def test_an_abbreviated_sha_is_accepted() -> None:
    """Render sends 40 characters; a hand-set value on another host may not.

    Seven is git's own abbreviation floor, and length does not weaken the
    property being defended: hexadecimal or nothing, either way.
    """

    assert commit_sha_or_none(A_COMMIT_SHA[:7]) == A_COMMIT_SHA[:7]


def test_the_environment_read_uses_the_variable_render_actually_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing else would notice this being wrong.

    A module reading an unset variable returns `None`, which is also what a
    correct module returns on every host that is not Render -- so a typo here
    looks exactly like a correct local run.
    """

    assert REVISION_ENV_VAR == "RENDER_GIT_COMMIT"
    monkeypatch.setenv("RENDER_GIT_COMMIT", A_COMMIT_SHA)
    assert deployed_revision() == A_COMMIT_SHA


def test_the_revision_is_not_settable_from_a_committed_file() -> None:
    """`Settings` reads `.env`; the deployed commit must not be configurable.

    A `revision` field on `Settings` could be set from a file in the working
    tree, and `get_settings` is `lru_cache`d, so it would also freeze at first
    call. Reading the environment directly is what keeps the value the
    platform's to state -- and keeps a bad one from reaching the production
    validator, which raises rather than degrading.
    """

    assert not hasattr(get_settings(), "revision")


# --------------------------------------------------------------------------- #
# Documentation
# --------------------------------------------------------------------------- #


def test_the_deployment_doc_explains_how_to_read_the_route() -> None:
    """Three answers, each meaning something different; 404 is the subtle one.

    Without the doc a 404 reads as "broken" rather than "the deployed build
    predates this route", which is the most useful thing the route can say to
    an operator chasing a deploy that did not land.
    """

    from pathlib import Path

    doc = (Path(__file__).resolve().parents[3] / "docs" / "PRODUCTION.md").read_text(
        encoding="utf-8"
    )
    assert VERSION_ROUTE in doc
    assert REVISION_ENV_VAR in doc
    assert "404" in doc


def test_the_pinned_health_body_is_the_one_the_app_builds() -> None:
    """Guards the guard: a stale literal would pin the wrong payload forever.

    `HEALTH_BODY` is written out by hand on purpose, so this is the one place
    the two are tied together -- if the package version is bumped, this fails
    and the literal is updated deliberately rather than the pin quietly
    protecting a payload nobody serves.
    """

    assert json.loads(HEALTH_BODY)["version"] == __version__
