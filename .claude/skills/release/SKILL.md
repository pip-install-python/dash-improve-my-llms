---
description: Build and verify a release of dash-improve-my-llms — runs the full sdist+wheel pipeline, installs the wheel in a temp venv, and confirms the public API is intact. Pass an optional bump type as argument (patch/minor/major).
argument-hint: <patch|minor|major|no-bump>
---

# Release dash-improve-my-llms

The user wants to cut a new release. Walk through the full pre-flight,
build, and verification sequence below. If $ARGUMENTS is `patch`,
`minor`, or `major`, propose the new version number. Otherwise, leave
the current version in `pyproject.toml` untouched.

## Step 1 — Pre-flight

Confirm the working tree is in a releasable state:

```bash
git status
```

Expected: clean tree, on the release branch (usually `main`).

Run the full test suite, skipping the legacy folder:

```bash
pytest tests/ --ignore=tests/legacy --tb=short -q
```

All tests must pass before continuing. If anything fails, stop and
report the failures to the user — do not proceed to build.

Boot-test the demo app to catch import errors that pytest might miss:

```bash
python -c "
import importlib.util, dash
dash.Dash.run = lambda *a, **k: None
spec = importlib.util.spec_from_file_location('app', 'app.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('app.py imports clean')
"
```

## Step 2 — Version

Read the current version from `pyproject.toml`:

```bash
grep "^version = " pyproject.toml
```

Read the top of `CHANGELOG.md` to confirm it has an entry for the
version being released. If $ARGUMENTS bumps the version, update both
`pyproject.toml` and `dash_improve_my_llms/__init__.py`'s
`__version__`. If there's no CHANGELOG entry for the new version,
stop and ask the user to write one.

## Step 3 — Clean old build artifacts

```bash
ls dist/
```

Note the existing artifacts but do NOT delete them — the user makes
that call. Just record what's there for the release report.

## Step 4 — Build

```bash
python -m build
```

Expected output: `Successfully built dash_improve_my_llms-X.Y.Z.tar.gz`
and the matching wheel.

## Step 5 — Verify the sdist

Confirm the tarball includes the right files and excludes the wrong
ones:

```bash
tar -tzf dist/dash_improve_my_llms-X.Y.Z.tar.gz | sort
```

Must include: `dash_improve_my_llms/__init__.py`, all adapters,
`handlers.py`, `_mcp_bridge.py`, `README.md`, `CHANGELOG.md`,
`docs/SKILLS.md` (or `SKILLS.md` if MANIFEST.in points to repo root),
`LICENSE`, `pyproject.toml`.

Must NOT include: `toon_generator.py`, `app.py`, `pages/`, `tests/`,
`.claude/`, `htmlcov/`, `.coverage`, `visitor_analytics.json`.

## Step 6 — Install the wheel in a temp venv

```bash
python -m venv /tmp/dimllm-rc
/tmp/dimllm-rc/bin/pip install --quiet dist/dash_improve_my_llms-X.Y.Z-py3-none-any.whl
/tmp/dimllm-rc/bin/python -c "
import dash_improve_my_llms as pkg
print(f'Version: {pkg.__version__}')
print(f'Public API: {sorted(pkg.__all__)}')
# Confirm dropped 1.x symbols stay dropped
for sym in ['TOONConfig', 'PageType', 'generate_llms_toon', 'extract_prose_content']:
    try:
        getattr(__import__('dash_improve_my_llms'), sym)
        print(f'  ✗ FAIL: {sym} should not be importable')
    except AttributeError:
        print(f'  ✓ {sym} correctly absent')
"
rm -rf /tmp/dimllm-rc
```

## Step 7 — Final report

Summarize for the user:

- Version released
- Tarball + wheel paths and sizes
- File counts and any surprises in the manifest
- Confirmation that public API matches `__all__`
- Confirmation that dropped 1.x symbols stay dropped
- Next manual steps: `twine upload dist/dash_improve_my_llms-X.Y.Z*`
  (do NOT run this — uploading is the user's call)
- Reminder to tag the git commit (`git tag vX.Y.Z`) AFTER PyPI accepts
  the upload

Do not run twine. Do not push tags. Hand it off cleanly with the
exact commands the user can copy.
