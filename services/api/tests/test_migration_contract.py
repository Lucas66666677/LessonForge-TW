"""`infra/start.sh` runs `alembic upgrade head` before the API ever binds a port.

Nothing else in the suite touches Alembic. `conftest.py` builds the schema with
`Base.metadata.create_all`, so the whole suite can pass green against a schema the
migration sequence would never produce. A second head left behind by two branches
landing in parallel, a revision naming a parent that was never merged, or a
migration that simply does not apply are all invisible to CI today -- and because
`start.sh` runs under `set -e`, each one turns into a container that exits before
serving a request, so Render keeps the old revision or the service stays down.

A release claiming migrations are ready therefore needs the upgrade path itself
proven, not just the models. These checks read the repo and migrate a throwaway
SQLite file under `tmp_path` -- no secrets, no network, no real database.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from alembic import command
from lessonforge.config import get_settings
from lessonforge.database import Base

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "services" / "api" / "alembic.ini"
ALEMBIC_DIR = REPO_ROOT / "services" / "api" / "alembic"

STUB_REVISION = '''"""stub revision"""

revision = "{revision}"
down_revision = {down_revision}
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
'''


def _config(script_location: Path | None = None) -> Config:
    """The real `alembic.ini`, optionally pointed at a copy of the migration tree.

    `script_location` is overridden rather than `version_locations`, which Alembic
    splits on whitespace and so cannot address a path containing a space.
    """
    config = Config(str(ALEMBIC_INI))
    if script_location is not None:
        config.set_main_option("script_location", str(script_location))
    return config


def sequence_problems(script_location: Path | None = None) -> list[str]:
    """Every reason `alembic upgrade head` would not be one walkable upgrade path."""
    try:
        directory = ScriptDirectory.from_config(_config(script_location))
        heads = directory.get_heads()
        walked = [revision.revision for revision in directory.walk_revisions()]
    except (KeyError, CommandError) as exc:
        # A parent revision that is not on disk surfaces as a raw KeyError carrying
        # the missing id; cycles and duplicate ids arrive as CommandError.
        return [f"the revision graph does not resolve: {exc!r}"]

    problems: list[str] = []
    if len(heads) != 1:
        problems.append(
            f"expected exactly one head, found {len(heads)}: {sorted(heads)}; "
            "`alembic upgrade head` refuses to run against a branched sequence"
        )

    version_files = sorted(
        path.name
        for path in Path(directory.versions).glob("*.py")
        if not path.name.startswith("__")
    )
    if len(walked) != len(version_files):
        problems.append(
            f"{len(version_files)} revision files exist but only {len(walked)} are on the "
            f"path from base to head: {version_files}"
        )
    return problems


def test_the_migration_sequence_is_one_walkable_upgrade_path() -> None:
    assert sequence_problems() == []


def test_upgrade_head_builds_every_model_table_and_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim under test: an empty database reaches head with the schema the app expects.

    `env.py` reads the URL through the cached settings, so the cache is cleared on
    both sides of the run to keep this test's throwaway database out of every other
    test's engine.
    """
    database_path = tmp_path / "migration-contract.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    try:
        command.upgrade(_config(), "head")
    finally:
        get_settings.cache_clear()

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            stamped = (
                connection.execute(sa.text("SELECT version_num FROM alembic_version"))
                .scalars()
                .all()
            )
            inspector = sa.inspect(connection)
            tables = set(inspector.get_table_names())
            columns = {
                name: {column["name"] for column in inspector.get_columns(name)}
                for name in Base.metadata.tables
                if name in tables
            }
    finally:
        engine.dispose()

    assert stamped == list(ScriptDirectory.from_config(_config()).get_heads()), (
        f"migrated database is stamped {stamped}, which is not the sequence head"
    )

    missing_tables = sorted(set(Base.metadata.tables) - tables)
    assert missing_tables == [], (
        f"`alembic upgrade head` did not create {missing_tables}; the models declare "
        "tables no migration builds, so production would boot against a schema that "
        "is missing them"
    )

    missing_columns = {
        name: sorted({column.name for column in table.columns} - columns[name])
        for name, table in Base.metadata.tables.items()
        if {column.name for column in table.columns} - columns[name]
    }
    assert missing_columns == {}, (
        f"`alembic upgrade head` left columns unbuilt: {missing_columns}; a model "
        "changed without a matching migration"
    )


@pytest.fixture
def migration_tree(tmp_path: Path) -> Path:
    """A copy of the real migration tree, ready to be broken one way at a time."""
    copy = tmp_path / "alembic"
    shutil.copytree(ALEMBIC_DIR, copy, ignore=shutil.ignore_patterns("__pycache__"))
    return copy


def test_a_second_head_is_reported(migration_tree: Path) -> None:
    """Two branches each adding a migration is how a sequence really breaks."""
    (migration_tree / "versions" / "parallel.py").write_text(
        STUB_REVISION.format(revision="0000parallel", down_revision="None"), encoding="utf-8"
    )
    assert any("exactly one head" in problem for problem in sequence_problems(migration_tree))


def test_a_revision_naming_an_absent_parent_is_reported(migration_tree: Path) -> None:
    """A revision whose parent never merged leaves the upgrade path unresolvable."""
    (migration_tree / "versions" / "orphan.py").write_text(
        STUB_REVISION.format(revision="0000orphan", down_revision='"0000nevermerged"'),
        encoding="utf-8",
    )
    problems = sequence_problems(migration_tree)
    assert any("does not resolve" in problem for problem in problems)
    assert any("0000nevermerged" in problem for problem in problems)
