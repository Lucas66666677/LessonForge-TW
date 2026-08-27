"""Fail the build when public demo credentials reappear in source or in a production bundle.

The published demo account and its shared password were removed in "security: remove
public demo credentials" (#3). Nothing in the toolchain stopped them from coming back:
a prefilled login form, a README credential block, or a bundled seed value would all
have shipped silently. This check is that stop.

It reads only files that are already in the repository or in the build output, so it
needs no secret, no environment access and no running service.

    python scripts/check_demo_credentials.py                     # source rules only
    python scripts/check_demo_credentials.py --build-dir dist    # source + bundle rules
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Credentials that were published once and must never reappear in any form.
# Append to this list whenever another credential is retired, so the gate keeps
# protecting every past incident rather than only the most recent one.
RETIRED_SECRETS = ("LessonForgeDemo!2026",)

# The seeded demo accounts. Their addresses may stay in server-side seeding and in
# tests, but must never reach browser-shipped source or the production bundle.
DEMO_ACCOUNT_DOMAIN = "@demo.lessonforge.tw"

DEMO_PASSWORD_KEYS = ("DEMO_OWNER_PASSWORD", "DEMO_TEACHER_PASSWORD")
DEMO_PASSWORD_SETTINGS = ("demo_owner_password", "demo_teacher_password")

# Directories whose contents are compiled into what the browser downloads.
SHIPPED_SOURCE_DIRS = ("app", "worker", "public")
SHIPPED_SOURCE_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".css", ".html", ".json")
# Vitest files live beside the components they cover and are never bundled.
TEST_FILE_PATTERN = re.compile(r"\.(test|spec)\.[jt]sx?$")

# Text formats worth reading inside a build directory. Images and fonts are skipped;
# everything textual, including source maps, is scanned.
BUILD_TEXT_SUFFIXES = (".js", ".mjs", ".cjs", ".json", ".html", ".css", ".txt", ".map")

# This file necessarily spells out the retired credential in order to detect it.
# It is the only exemption; tests reach the value through RETIRED_SECRETS instead.
SELF_EXEMPT = ("scripts/check_demo_credentials.py",)

DEMO_PASSWORD_ASSIGNMENT = re.compile(
    r"(?:^|[\s\"',;{(])(DEMO_[A-Z_]*PASSWORD)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|[^\s\"',;})]+)"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_shipped_sources(root: Path) -> Iterator[Path]:
    for directory in SHIPPED_SOURCE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in SHIPPED_SOURCE_SUFFIXES:
                continue
            if TEST_FILE_PATTERN.search(path.name):
                continue
            yield path


def _iter_build_files(build_dir: Path) -> Iterator[Path]:
    for path in sorted(build_dir.rglob("*")):
        if path.is_file() and path.suffix in BUILD_TEXT_SUFFIXES:
            yield path


def _iter_tracked_text(root: Path) -> Iterator[Path]:
    """Files a retired credential could plausibly be pasted back into."""
    yield from _iter_shipped_sources(root)
    for name in ("README.md", ".env.example"):
        yield root / name
    for directory, pattern in (
        ("docs", "*.md"),
        ("scripts", "*.py"),
        ("services", "*.py"),
        ("e2e", "*.ts"),
        ("app", "*.test.tsx"),
    ):
        base = root / directory
        if base.is_dir():
            yield from sorted(base.rglob(pattern))


def check_retired_secrets(root: Path) -> list[str]:
    """No retired credential may survive anywhere a reader or a bundler can reach."""
    failures: list[str] = []
    for path in _iter_tracked_text(root):
        if not path.is_file() or _rel(path, root) in SELF_EXEMPT:
            continue
        text = _read(path)
        for secret in RETIRED_SECRETS:
            if secret in text:
                failures.append(
                    f"{_rel(path, root)}: contains the retired demo password "
                    f"{secret!r}; it was published once and must not return."
                )
    return failures


def check_env_example(root: Path) -> list[str]:
    """`.env.example` documents the demo keys but must never carry a usable value."""
    path = root / ".env.example"
    if not path.is_file():
        return [".env.example: missing; the demo credential keys cannot be verified."]
    values: dict[str, str] = {}
    for line in _read(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    failures: list[str] = []
    for key in DEMO_PASSWORD_KEYS:
        if key not in values:
            failures.append(f".env.example: {key} is no longer documented.")
        elif values[key]:
            failures.append(
                f".env.example: {key} has the value {values[key]!r}; demo passwords "
                "must stay empty so every operator sets a unique local one."
            )
    return failures


def check_settings_defaults(root: Path) -> list[str]:
    """A non-empty settings default would ship a shared password inside the image."""
    path = root / "services" / "api" / "lessonforge" / "config.py"
    if not path.is_file():
        return [f"{_rel(path, root)}: missing; demo settings defaults cannot be verified."]
    text = _read(path)
    failures: list[str] = []
    for field in DEMO_PASSWORD_SETTINGS:
        match = re.search(rf"^\s*{field}\s*:\s*str\s*=\s*(.+)$", text, re.MULTILINE)
        if match is None:
            failures.append(f"{_rel(path, root)}: {field} is no longer declared.")
        elif match.group(1).strip() not in {'""', "''"}:
            failures.append(
                f"{_rel(path, root)}: {field} defaults to {match.group(1).strip()}; "
                "it must default to an empty string."
            )
    return failures


def _check_login_defaults(root: Path) -> list[str]:
    path = root / "app" / "pages" / "LoginPage.tsx"
    if not path.is_file():
        return [f"{_rel(path, root)}: missing; login prefill cannot be verified."]
    block = re.search(r"defaultValues\s*:\s*\{(.*?)\}", _read(path), re.DOTALL)
    if block is None:
        return [f"{_rel(path, root)}: no defaultValues block found to verify."]
    failures: list[str] = []
    for field in ("email", "password"):
        match = re.search(rf"\b{field}\s*:\s*(\"[^\"]*\"|'[^']*'|`[^`]*`)", block.group(1))
        if match is not None and match.group(1)[1:-1]:
            failures.append(
                f"{_rel(path, root)}: the login form prefills {field} with "
                f"{match.group(1)}; both fields must start empty."
            )
    return failures


def check_shipped_sources(root: Path) -> list[str]:
    """Browser-shipped source must not name a demo account or prefill the login form."""
    failures: list[str] = []
    for path in _iter_shipped_sources(root):
        text = _read(path)
        if DEMO_ACCOUNT_DOMAIN in text:
            failures.append(
                f"{_rel(path, root)}: names a {DEMO_ACCOUNT_DOMAIN} account in "
                "browser-shipped source; demo accounts must not be advertised to visitors."
            )
        for match in DEMO_PASSWORD_ASSIGNMENT.finditer(text):
            if match.group(2).strip("\"'"):
                failures.append(f"{_rel(path, root)}: assigns {match.group(1)} a literal value.")
    failures.extend(_check_login_defaults(root))
    return failures


def check_seed_production_guard(root: Path) -> list[str]:
    """Seeding must stay refused under APP_ENV=production."""
    path = root / "scripts" / "seed.py"
    if not path.is_file():
        return [f"{_rel(path, root)}: missing; the production seed guard cannot be verified."]
    if not re.search(r"app_env\s*==\s*[\"']production[\"']", _read(path)):
        return [
            f"{_rel(path, root)}: no APP_ENV=production guard; demo accounts could be "
            "seeded into a production database."
        ]
    return []


def check_build_output(build_dir: Path, root: Path) -> list[str]:
    """The production bundle is the last place a credential can escape from."""
    if not build_dir.is_dir():
        return [f"{_rel(build_dir, root)}: build directory not found; run the build first."]
    failures: list[str] = []
    scanned = 0
    for path in _iter_build_files(build_dir):
        scanned += 1
        text = _read(path)
        for secret in RETIRED_SECRETS:
            if secret in text:
                failures.append(
                    f"{_rel(path, root)}: the production bundle contains the retired "
                    f"demo password {secret!r}."
                )
        if DEMO_ACCOUNT_DOMAIN in text:
            failures.append(
                f"{_rel(path, root)}: the production bundle contains a "
                f"{DEMO_ACCOUNT_DOMAIN} account address."
            )
        for match in DEMO_PASSWORD_ASSIGNMENT.finditer(text):
            if match.group(2).strip("\"'"):
                failures.append(
                    f"{_rel(path, root)}: the production bundle inlines "
                    f"{match.group(1)} with a literal value."
                )
    if scanned == 0:
        failures.append(
            f"{_rel(build_dir, root)}: no scannable build files; the bundle check would "
            "otherwise pass without inspecting anything."
        )
    return failures


def run_checks(root: Path, build_dir: Path | None = None) -> list[str]:
    failures = [
        *check_retired_secrets(root),
        *check_env_example(root),
        *check_settings_defaults(root),
        *check_shipped_sources(root),
        *check_seed_production_guard(root),
    ]
    if build_dir is not None:
        failures.extend(check_build_output(build_dir, root))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reject public demo credentials in source and production builds."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Production build output to scan, for example dist.",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    build_dir = (root / args.build_dir).resolve() if args.build_dir is not None else None

    failures = run_checks(root, build_dir)
    if failures:
        print("Public demo credentials would ship. Fix these before releasing:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    scope = "source and production bundle" if build_dir is not None else "source"
    print(f"No public demo credentials found in {scope}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
