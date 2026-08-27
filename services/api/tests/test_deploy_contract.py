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

from pathlib import Path
from typing import Any

import yaml
from fastapi.testclient import TestClient

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
