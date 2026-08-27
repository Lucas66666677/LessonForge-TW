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
