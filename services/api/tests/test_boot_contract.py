"""The container boot path -- `render.yaml` -> Dockerfile `CMD` -> `infra/start.sh`.

`test_migration_contract.py` proves `alembic upgrade head` *would* work, and
`test_deploy_contract.py` proves the health route Render polls answers. Neither reads
the script that actually runs at boot, so the premise both rest on -- that a released
container migrates before it serves -- is untested. Dropping the `alembic` line, losing
`set -e`, moving `scripts/seed.py`, or renaming the uvicorn target all keep the suite
green while production either exits before binding a port (`set -e` on a missing file)
or, worse, serves traffic against an unmigrated schema.

These checks read only the repo -- no secrets, no network, no Docker build -- and
resolve the same paths the container does, since `api.Dockerfile` copies the repo to
the `/app` working directory the script's relative paths are written against.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

from lessonforge.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = REPO_ROOT / "render.yaml"

MIGRATE = re.compile(r"\balembic\b.*\bupgrade\s+(?P<target>\S+)")
ALEMBIC_CONFIG = re.compile(r"\balembic\b.*?-c\s+(?P<config>\S+)")
SERVE = re.compile(r"\buvicorn\s+(?P<module>[\w.]+):(?P<attribute>\w+)")
SCRIPT_ARGUMENT = re.compile(r"\bpython\s+(?P<path>[^\s&|;]+\.py)")
MODULE_ARGUMENT = re.compile(r"\bpython\s+-m\s+(?P<module>[\w.]+)")
ABORT_ON_ERROR = re.compile(r"^set\s+-[a-z]*e")


def _web_service() -> dict[str, Any]:
    document = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    web_services = [service for service in document["services"] if service.get("type") == "web"]
    assert len(web_services) == 1, f"expected exactly one web service, found {len(web_services)}"
    return web_services[0]


def _dockerfile() -> Path:
    """The Dockerfile Render actually builds, named by `render.yaml`."""
    return REPO_ROOT / _web_service()["dockerfilePath"].lstrip("./")


def _container_command() -> list[str]:
    """The argv of the last `CMD` in that Dockerfile, exec or shell form."""
    dockerfile = _dockerfile()
    commands = [
        stripped[len("CMD") :].strip()
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()).startswith("CMD")
    ]
    assert commands, f"{dockerfile.name} declares no CMD; the container has nothing to run"
    command = commands[-1]
    if command.startswith("["):
        return [str(token) for token in json.loads(command)]
    return shlex.split(command)


def start_script_path() -> Path:
    """The shell script the container command hands to `sh`."""
    command = _container_command()
    scripts = [token for token in command if token.endswith(".sh")]
    assert len(scripts) == 1, (
        f"expected the container CMD to name exactly one shell script, got {command}"
    )
    return REPO_ROOT / scripts[0]


def boot_steps(script_text: str) -> list[str]:
    """The commands the script runs, in order, with comments and blank lines dropped."""
    return [
        stripped
        for line in script_text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]


def boot_order_problems(script_text: str) -> list[str]:
    """Every reason a released container could end up serving an unmigrated schema."""
    steps = boot_steps(script_text)
    problems: list[str] = []

    if not any(ABORT_ON_ERROR.match(step) for step in steps):
        problems.append(
            "the script never runs `set -e`, so a failed migration is ignored and the "
            "server starts anyway against whatever schema the database happens to have"
        )

    migrations = [index for index, step in enumerate(steps) if MIGRATE.search(step)]
    servers = [index for index, step in enumerate(steps) if SERVE.search(step)]

    if not migrations:
        problems.append(
            "no step runs `alembic upgrade`; the container boots against whatever schema "
            "the database already has, so a release ships its models without its migrations"
        )
    if not servers:
        problems.append("no step starts uvicorn; the container would exit without serving")
    if migrations and servers and min(migrations) > min(servers):
        problems.append(
            f"the first server start ({steps[min(servers)]!r}) comes before the migration "
            f"({steps[min(migrations)]!r}); traffic would be served on the old schema"
        )

    problems.extend(
        f"{steps[index]!r} does not upgrade to `head`, so the schema stops short of the "
        "revision the models are written against"
        for index in migrations
        if (match := MIGRATE.search(steps[index])) and match.group("target") != "head"
    )
    return problems


def test_the_container_command_runs_a_start_script_that_exists() -> None:
    """`render.yaml` -> Dockerfile -> start script has to resolve on disk.

    The existing deploy contract stops at the Dockerfile. If the script it hands to `sh`
    is renamed or moved, the image still builds and every container exits immediately,
    which Render surfaces only as a failed health check on a deploy that never promotes.
    """
    script = start_script_path()
    assert script.is_file(), (
        f"the container CMD {_container_command()} names a start script that does not "
        f"exist at {script.relative_to(REPO_ROOT).as_posix()!r}"
    )


def test_the_release_migrates_before_it_serves() -> None:
    assert boot_order_problems(start_script_path().read_text(encoding="utf-8")) == []


def test_the_migration_step_names_a_config_file_that_exists() -> None:
    """`alembic -c <path>` resolves from the image's working directory.

    `api.Dockerfile` copies the repo to `/app` and runs the script from there, so the
    path is repo-relative. Moving `alembic.ini` without updating the script leaves a
    container that dies under `set -e` before binding a port.
    """
    for step in boot_steps(start_script_path().read_text(encoding="utf-8")):
        match = ALEMBIC_CONFIG.search(step)
        if match is None:
            continue
        config = REPO_ROOT / match.group("config")
        assert config.is_file(), (
            f"the boot step {step!r} names alembic config {match.group('config')!r}, which "
            "does not exist in the repo the image is built from"
        )


def test_every_boot_step_names_a_file_or_module_that_exists() -> None:
    """Under `set -e`, one missing path is the difference between a release and an outage.

    Modules are resolved with `find_spec` rather than imported: `lessonforge.worker`
    opens a Redis connection when it runs, and what matters here is that the container
    can find it, not that this process can run it.
    """
    for step in boot_steps(start_script_path().read_text(encoding="utf-8")):
        for script_match in SCRIPT_ARGUMENT.finditer(step):
            script = REPO_ROOT / script_match.group("path")
            assert script.is_file(), (
                f"the boot step {step!r} runs {script_match.group('path')!r}, which does not "
                "exist; `set -e` stops the container there, before it serves a request"
            )
        for module_match in MODULE_ARGUMENT.finditer(step):
            module_name = module_match.group("module")
            assert importlib.util.find_spec(module_name) is not None, (
                f"the boot step {step!r} runs `python -m {module_name}`, which is not importable"
            )


def test_the_start_script_serves_the_application_the_suite_tests() -> None:
    """Every uvicorn target has to be the app the rest of the suite exercises.

    `test_deploy_contract.py` proves Render's health path answers on `lessonforge.main:app`.
    That evidence only covers production if the container starts that exact object, so a
    target pointed at another module -- or at an app attribute that no longer exists --
    fails here instead of passing CI and serving something unproven.
    """
    targets = [
        match
        for step in boot_steps(start_script_path().read_text(encoding="utf-8"))
        if (match := SERVE.search(step))
    ]
    assert targets, "the start script names no uvicorn target"

    for match in targets:
        module_name, attribute = match.group("module"), match.group("attribute")
        module = importlib.import_module(module_name)
        assert getattr(module, attribute, None) is app, (
            f"the start script serves {module_name}:{attribute}, which is not the "
            "`lessonforge.main:app` the deploy and health checks are proven against"
        )


@pytest.mark.parametrize(
    ("broken_script", "expected"),
    [
        pytest.param(
            "#!/bin/sh\nset -e\nuvicorn lessonforge.main:app\npython -m alembic upgrade head\n",
            "comes before the migration",
            id="serves-before-migrating",
        ),
        pytest.param(
            "#!/bin/sh\npython -m alembic upgrade head\nuvicorn lessonforge.main:app\n",
            "`set -e`",
            id="ignores-a-failed-migration",
        ),
        pytest.param(
            "#!/bin/sh\nset -e\nuvicorn lessonforge.main:app\n",
            "no step runs `alembic upgrade`",
            id="ships-models-without-migrations",
        ),
        pytest.param(
            "#!/bin/sh\nset -e\n# python -m alembic upgrade head\nuvicorn lessonforge.main:app\n",
            "no step runs `alembic upgrade`",
            id="migration-commented-out",
        ),
        pytest.param(
            "#!/bin/sh\nset -e\npython -m alembic upgrade 0001\nuvicorn lessonforge.main:app\n",
            "does not upgrade to `head`",
            id="stops-short-of-head",
        ),
    ],
)
def test_a_boot_order_regression_is_reported(broken_script: str, expected: str) -> None:
    """The ways this really breaks: a reordered, dropped, unguarded, or partial migration."""
    assert any(expected in problem for problem in boot_order_problems(broken_script))
