"""The demo-credential gate must fail on every way the credentials could come back.

A guard that only passes is worthless, so each rule is exercised against a synthetic
tree where exactly one regression has been introduced. The retired password itself is
read from the checker rather than repeated here, so this file never carries it.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKER_PATH = REPO_ROOT / "scripts" / "check_demo_credentials.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_demo_credentials", CHECKER_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging accident
        raise RuntimeError(f"cannot load {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_checker()
RETIRED = guard.RETIRED_SECRETS[0]

CLEAN_ENV_EXAMPLE = """APP_ENV=development
DEMO_OWNER_EMAIL=owner@demo.lessonforge.tw
DEMO_OWNER_PASSWORD=
DEMO_TEACHER_EMAIL=teacher@demo.lessonforge.tw
DEMO_TEACHER_PASSWORD=
"""

CLEAN_CONFIG = """class Settings(BaseSettings):
    demo_owner_email: str = "owner@demo.lessonforge.tw"
    demo_owner_password: str = ""
    demo_teacher_email: str = "teacher@demo.lessonforge.tw"
    demo_teacher_password: str = ""
"""

CLEAN_LOGIN_PAGE = """export function LoginPage() {
  const form = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      password: "",
    },
  });
  return <form />;
}
"""

CLEAN_SEED = """if __name__ == "__main__":
    if get_settings().app_env == "production":
        print("Skipping demo seed")
    else:
        asyncio.run(seed())
"""

CLEAN_BUNDLE = 'const t="\\u767b\\u5165";export{t};\n'


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    """A minimal tree that satisfies every rule, ready to be broken one rule at a time."""
    root = tmp_path / "repo"
    (root / "app" / "pages").mkdir(parents=True)
    (root / "services" / "api" / "lessonforge").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    (root / "dist" / "client").mkdir(parents=True)

    (root / ".env.example").write_text(CLEAN_ENV_EXAMPLE, encoding="utf-8")
    (root / "README.md").write_text("# LessonForge TW\n", encoding="utf-8")
    (root / "app" / "pages" / "LoginPage.tsx").write_text(CLEAN_LOGIN_PAGE, encoding="utf-8")
    (root / "services" / "api" / "lessonforge" / "config.py").write_text(
        CLEAN_CONFIG, encoding="utf-8"
    )
    (root / "scripts" / "seed.py").write_text(CLEAN_SEED, encoding="utf-8")
    (root / "dist" / "client" / "index.js").write_text(CLEAN_BUNDLE, encoding="utf-8")
    yield root


def failures(root: Path) -> list[str]:
    return guard.run_checks(root, root / "dist")


def test_clean_tree_passes(repo: Path) -> None:
    assert failures(repo) == []


def test_this_repository_has_no_public_demo_credentials() -> None:
    """The gate's reason for existing: the real tree must stay clean."""
    assert guard.run_checks(REPO_ROOT) == []


def test_retired_password_in_shipped_source_is_rejected(repo: Path) -> None:
    (repo / "app" / "pages" / "Hint.tsx").write_text(
        f'export const hint = "{RETIRED}";\n', encoding="utf-8"
    )
    assert any("retired demo password" in failure for failure in failures(repo))


def test_retired_password_in_documentation_is_rejected(repo: Path) -> None:
    (repo / "README.md").write_text(f"Password: `{RETIRED}`\n", encoding="utf-8")
    assert any("README.md" in failure for failure in failures(repo))


def test_demo_password_value_in_env_example_is_rejected(repo: Path) -> None:
    (repo / ".env.example").write_text(
        CLEAN_ENV_EXAMPLE.replace("DEMO_OWNER_PASSWORD=", "DEMO_OWNER_PASSWORD=shared-demo-pw"),
        encoding="utf-8",
    )
    assert any("DEMO_OWNER_PASSWORD" in failure for failure in failures(repo))


def test_missing_demo_password_key_is_reported(repo: Path) -> None:
    (repo / ".env.example").write_text("APP_ENV=development\n", encoding="utf-8")
    assert len([f for f in failures(repo) if "no longer documented" in f]) == 2


def test_non_empty_settings_default_is_rejected(repo: Path) -> None:
    (repo / "services" / "api" / "lessonforge" / "config.py").write_text(
        CLEAN_CONFIG.replace('demo_teacher_password: str = ""', 'demo_teacher_password: str = "x"'),
        encoding="utf-8",
    )
    assert any("demo_teacher_password defaults to" in failure for failure in failures(repo))


def test_prefilled_login_form_is_rejected(repo: Path) -> None:
    (repo / "app" / "pages" / "LoginPage.tsx").write_text(
        CLEAN_LOGIN_PAGE.replace('password: ""', 'password: "prefilled"'),
        encoding="utf-8",
    )
    assert any("prefills password" in failure for failure in failures(repo))


def test_demo_account_address_in_shipped_source_is_rejected(repo: Path) -> None:
    (repo / "app" / "pages" / "Banner.tsx").write_text(
        'export const owner = "owner@demo.lessonforge.tw";\n', encoding="utf-8"
    )
    assert any("Banner.tsx" in failure for failure in failures(repo))


def test_component_test_files_may_reference_demo_accounts(repo: Path) -> None:
    """Vitest files sit next to components but are never bundled."""
    (repo / "app" / "pages" / "LoginPage.test.tsx").write_text(
        'const email = "owner@demo.lessonforge.tw";\n', encoding="utf-8"
    )
    assert failures(repo) == []


def test_removed_production_seed_guard_is_rejected(repo: Path) -> None:
    (repo / "scripts" / "seed.py").write_text("asyncio.run(seed())\n", encoding="utf-8")
    assert any("APP_ENV=production guard" in failure for failure in failures(repo))


def test_retired_password_in_production_bundle_is_rejected(repo: Path) -> None:
    (repo / "dist" / "client" / "chunk.js").write_text(f'const p="{RETIRED}";\n', encoding="utf-8")
    assert any("production bundle contains the retired" in failure for failure in failures(repo))


def test_demo_account_address_in_production_bundle_is_rejected(repo: Path) -> None:
    (repo / "dist" / "client" / "chunk.js").write_text(
        'const e="teacher@demo.lessonforge.tw";\n', encoding="utf-8"
    )
    assert any("account address" in failure for failure in failures(repo))


def test_inlined_demo_password_variable_in_bundle_is_rejected(repo: Path) -> None:
    (repo / "dist" / "client" / "env.js").write_text(
        'window.ENV={DEMO_OWNER_PASSWORD:"leaked-value"};\n', encoding="utf-8"
    )
    assert any("inlines DEMO_OWNER_PASSWORD" in failure for failure in failures(repo))


def test_empty_demo_password_variable_in_bundle_is_allowed(repo: Path) -> None:
    (repo / "dist" / "client" / "env.js").write_text(
        'window.ENV={DEMO_OWNER_PASSWORD:""};\n', encoding="utf-8"
    )
    assert failures(repo) == []


def test_retired_password_in_extensionless_build_file_is_rejected(repo: Path) -> None:
    """`_headers` and `BUILD_ID` ship with the bundle and carry no suffix to match on."""
    (repo / "dist" / "client" / "_headers").write_text(
        f"/*\n  X-Demo-Password: {RETIRED}\n", encoding="utf-8"
    )
    assert any("_headers" in failure for failure in failures(repo))


def test_demo_account_address_in_bundled_svg_is_rejected(repo: Path) -> None:
    """An SVG is text the browser downloads, so a credential in one is a credential shipped."""
    (repo / "dist" / "client" / "og.svg").write_text(
        "<svg><!-- owner@demo.lessonforge.tw --></svg>\n", encoding="utf-8"
    )
    assert any("og.svg" in failure for failure in failures(repo))


def test_binary_build_assets_are_skipped(repo: Path) -> None:
    """Fonts and images cannot be read as text; scanning them must not fail the build."""
    (repo / "dist" / "client" / "geist.woff2").write_bytes(b"wOF2" + bytes(2) + RETIRED.encode())
    (repo / "dist" / "client" / "og.png").write_bytes(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
    assert failures(repo) == []


def test_unsuffixed_binary_build_file_is_skipped(repo: Path) -> None:
    """A binary with no suffix is detected by content rather than by name."""
    (repo / "dist" / "client" / "blob").write_bytes(bytes([0, 1, 2]) + b"binary")
    assert failures(repo) == []


def test_missing_build_directory_is_rejected(repo: Path) -> None:
    """A build that never ran must not be mistaken for a build that is clean."""
    assert any(
        "build directory not found" in failure
        for failure in guard.run_checks(repo, repo / "no-such-dir")
    )


def test_empty_build_directory_is_rejected(repo: Path) -> None:
    (repo / "dist" / "client" / "index.js").unlink()
    assert any("no scannable build files" in failure for failure in failures(repo))


def test_main_reports_the_failure_and_exits_non_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "app" / "pages" / "Leak.tsx").write_text(
        f'export const p = "{RETIRED}";\n', encoding="utf-8"
    )
    exit_code = guard.main(["--root", str(repo), "--build-dir", "dist"])
    assert exit_code == 1
    assert "Public demo credentials would ship" in capsys.readouterr().out


def test_main_passes_on_a_clean_tree(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = guard.main(["--root", str(repo), "--build-dir", "dist"])
    assert exit_code == 0
    assert "No public demo credentials" in capsys.readouterr().out
