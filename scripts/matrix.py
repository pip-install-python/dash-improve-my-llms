#!/usr/bin/env python
"""
Run the smoke test against every supported Dash version.

Creates one throwaway virtualenv per version under a cache directory,
installs that Dash plus the backend extras and this package, then runs
`scripts/smoke_test.py` inside it. Environments are reused between runs, so
the first invocation is slow and later ones are quick.

    python scripts/matrix.py                 # every supported version
    python scripts/matrix.py 4.3.0 4.4.1     # just these
    python scripts/matrix.py --recreate      # rebuild the environments

CI runs the same smoke test through a job matrix instead; this exists so the
matrix can be reproduced locally without pushing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# The supported range. Dash 4.1.0 is the floor because that is where the
# package's Dash 4 support starts; it is Flask-only, which the smoke test
# detects and reports rather than treating as a failure.
DASH_VERSIONS = ["4.1.0", "4.2.0", "4.3.0", "4.4.0", "4.4.1"]

REPO = Path(__file__).resolve().parent.parent
ENV_ROOT = Path(os.environ.get("DIMLL_MATRIX_HOME", REPO / ".matrix-envs"))

GREEN, RED, BOLD, DIM, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[2m", "\033[0m"


def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def ensure_env(version: str, recreate: bool) -> Path:
    env_dir = ENV_ROOT / f"dash-{version}"
    python = env_dir / "bin" / "python"

    if recreate and env_dir.exists():
        shutil.rmtree(env_dir)

    if not python.exists():
        print(f"{DIM}  creating {env_dir}{RESET}")
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        run([sys.executable, "-m", "venv", str(env_dir)], check=True)

    print(f"{DIM}  installing dash=={version}{RESET}")

    # Prefer Dash's own backend extras: `fastapi` alone is not enough for
    # dash.backends._fastapi to import, and installing the wrong set makes a
    # usable backend look broken. 4.1.0 predates the extras, so fall back.
    base = [
        str(python),
        "-m",
        "pip",
        "install",
        "-q",
        "--disable-pip-version-check",
    ]
    common = ["httpx", "pytest", "pytest-asyncio"]
    result = run(
        base + [f"dash[fastapi,quart]=={version}"] + common, capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"{DIM}  no backend extras for {version}; installing bare dash{RESET}")
        result = run(base + [f"dash=={version}", "flask"] + common, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"{RED}  pip failed for dash=={version}{RESET}")
        print(result.stdout[-2000:])
        print(result.stderr[-2000:])
        raise SystemExit(1)

    # Install the package last and without deps, so nothing here can quietly
    # upgrade the Dash version we are trying to test.
    run(
        [str(python), "-m", "pip", "install", "-q", "--no-deps", "-e", str(REPO)],
        check=True,
    )
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("versions", nargs="*", default=None)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument(
        "--pytest",
        action="store_true",
        help="Also run the pytest suite in each environment.",
    )
    args = parser.parse_args()

    versions = args.versions or DASH_VERSIONS
    results = {}

    for version in versions:
        print(f"\n{BOLD}=== dash {version} ==={RESET}")
        python = ensure_env(version, args.recreate)

        smoke = run([str(python), str(REPO / "scripts" / "smoke_test.py")])
        ok = smoke.returncode == 0

        if ok and args.pytest:
            pytest_run = run(
                [
                    str(python),
                    "-m",
                    "pytest",
                    str(REPO / "tests"),
                    "--ignore",
                    str(REPO / "tests" / "legacy"),
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=REPO,
            )
            ok = pytest_run.returncode == 0

        results[version] = ok

    print(f"\n{BOLD}=== summary ==={RESET}")
    for version, ok in results.items():
        badge = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  dash {version:<8} {badge}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
