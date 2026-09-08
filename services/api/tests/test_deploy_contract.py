"""The Render deploy contract in `render.yaml` must agree with the running app.

Render gates every deploy on `healthCheckPath`: if that path does not return a 2xx,
the new revision is never promoted and production silently stays on the old build (or
goes down) with no failing test to warn us. Nothing else in the suite exercises the
app *through the path the deploy contract names*, so renaming the health route or
letting `render.yaml` drift would pass CI and only surface as a stuck deploy.

These checks read only the repo and the in-process app -- no secrets, no network, no
Render API -- so they run anywhere the rest of the suite does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from lessonforge.database import get_session
from lessonforge.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = REPO_ROOT / "render.yaml"


def _web_service() -> dict[str, Any]:
    document = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    services = document["services"]
    web_services = [service for service in services if service.get("type") == "web"]
    assert len(web_services) == 1, f"expected exactly one web service, found {len(web_services)}"
    return web_services[0]


def test_render_healthcheck_path_is_a_live_2xx_route() -> None:
    health_path = _web_service()["healthCheckPath"]
    assert health_path.startswith("/"), f"healthCheckPath must be an absolute path, got {health_path!r}"

    with TestClient(app) as client:
        response = client.get(health_path)

    assert response.status_code == 200, (
        f"render.yaml healthCheckPath {health_path!r} did not return 200 "
        f"(got {response.status_code}); Render would fail every deploy"
    )


def test_render_dockerfile_path_exists() -> None:
    dockerfile_path = _web_service()["dockerfilePath"]
    resolved = (REPO_ROOT / dockerfile_path.lstrip("./")).resolve()
    assert resolved.is_file(), f"render.yaml dockerfilePath {dockerfile_path!r} does not exist"


def test_render_healthcheck_path_is_a_declared_route() -> None:
    """The deploy gate must name a route the app actually declares.

    `test_render_healthcheck_path_is_a_live_2xx_route` only asserts *a* 200 comes
    back, which a catch-all or a redirect could satisfy. Render promotes a revision
    only when the named path answers, so the path has to be a first-class GET route
    on the app -- deleting or renaming the handler must fail here, not in production.
    """
    health_path = _web_service()["healthCheckPath"]

    declared_get_routes = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and "GET" in (route.methods or set())
    }

    assert health_path in declared_get_routes, (
        f"render.yaml healthCheckPath {health_path!r} is not a declared GET route; "
        f"declared routes: {sorted(declared_get_routes)}"
    )


def test_render_healthcheck_is_liveness_not_readiness() -> None:
    """The deploy gate must not depend on a database that can be degraded.

    A readiness probe reports "can this instance serve traffic", so it fails while a
    dependency is slow or down. Pointing `healthCheckPath` at one makes every deploy
    hostage to the database: a transient Postgres blip during rollout marks the new
    revision unhealthy and production silently stays on the old build. The health
    gate therefore has to be liveness -- answerable by the process alone.

    The dependency override stands in for a down database: it fails any route that
    injects a session, so repointing `healthCheckPath` at a readiness-style route
    fails here instead of stalling a deploy.
    """
    health_path = _web_service()["healthCheckPath"]

    async def _unavailable_database() -> AsyncIterator[None]:
        raise RuntimeError("database unavailable")
        yield  # pragma: no cover - unreachable, keeps the dependency a generator

    app.dependency_overrides[get_session] = _unavailable_database
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(health_path)
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 200, (
        f"render.yaml healthCheckPath {health_path!r} returned {response.status_code} "
        "with the database unavailable; the deploy gate must be a liveness endpoint, "
        "not a dependency-sensitive readiness endpoint"
    )

    health_route = next(
        route for route in app.routes if isinstance(route, APIRoute) and route.path == health_path
    )
    assert health_route.dependant.dependencies == [], (
        f"healthCheckPath {health_path!r} declares injected dependencies "
        "-- a liveness route must not depend on anything that can be down"
    )


def _service_env(service: dict[str, Any]) -> dict[str, Any]:
    """The `key: ...` entries of a service's envVars, indexed by key.

    An entry may carry `value`, or a generator such as `generateValue` /
    `fromDatabase`. Both count as declared; a key absent from the blueprint is
    not, and Render never prompts for it on a sync.
    """
    entries = service.get("envVars") or []
    return {
        str(entry["key"]): entry
        for entry in entries
        if isinstance(entry, dict) and "key" in entry
    }


def test_render_service_tracks_main_and_redeploys_on_commit() -> None:
    """A merged fix has to actually reach the running service.

    Every other rule in this file checks what the deploy *does* once it runs.
    None of them checks whether a commit triggers one at all. Those two fields
    are the entire answer to "is the deployed API the code on `main`?", and
    without them a green merge can leave the service on an old image
    indefinitely while CI keeps reporting success -- a silent drift that has
    already cost a sibling product a shipped fix.

    Both are plain configuration, no secret, so neither has a reason to be
    absent.
    """
    service = _web_service()

    assert service.get("branch") == "main", (
        f"render.yaml pins branch {service.get('branch')!r}; the deploy must track `main`, "
        "or what reaches production is not answerable from this repository"
    )
    assert service.get("autoDeployTrigger") == "commit", (
        f"render.yaml sets autoDeployTrigger {service.get('autoDeployTrigger')!r}; without "
        "`commit` a change merged to main may never be built and the service keeps serving "
        "its previous image while CI reports green"
    )


def test_render_declares_the_generation_provider() -> None:
    """The blueprint must say which LLM provider the deployment runs.

    `Settings.llm_provider` defaults to `mock`, so a blueprint that omits
    `LLM_PROVIDER` produces a deployment that quietly generates mock lessons
    while nothing in the repository records that. Declaring it keeps the
    deployed provider state reviewable in code -- and reviewable is the point:
    this deployment currently declares `mock`, which is a real product state,
    not an accident to be discovered by a user.
    """
    environment = _service_env(_web_service())

    assert "LLM_PROVIDER" in environment, (
        "render.yaml declares no LLM_PROVIDER; Settings.llm_provider then falls back to "
        "'mock' and the deployment generates mock lessons with nothing in the repository "
        "saying so"
    )


def test_render_generation_provider_is_one_the_settings_accept() -> None:
    """A provider the settings reject stops the container at boot.

    `llm_provider` is a `Literal`, so pydantic refuses an unlisted value while
    `Settings` is being built -- inside `lifespan`, i.e. as a deploy that never
    turns its health gate green. The accepted values are read off the real
    field rather than copied, so widening the Literal cannot leave this stale.
    """
    from typing import get_args

    from lessonforge.config import Settings

    accepted = set(get_args(Settings.model_fields["llm_provider"].annotation))
    assert accepted, "could not read the accepted llm_provider values off Settings"

    declared = _service_env(_web_service())["LLM_PROVIDER"].get("value")
    assert declared in accepted, (
        f"render.yaml sets LLM_PROVIDER={declared!r}, which Settings.llm_provider does not "
        f"accept (allowed: {sorted(accepted)}); the container would fail to start"
    )
