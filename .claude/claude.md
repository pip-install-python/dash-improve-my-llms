# dash-improve-my-llms — project instructions

This repository is the home of **dash-improve-my-llms 2.0**, a
crawler/SEO companion for Dash apps with a thin MCP bridge for
Dash 4.3+. The repo doubles as the example/test bed: a full demo
Dash app in `app.py` + `pages/` exercises every part of the package.

## Mental model

Three audiences, only one of which Dash 4.3 MCP covers natively:

| Audience              | How they reach the app          | What we serve them                            |
|-----------------------|---------------------------------|-----------------------------------------------|
| MCP clients           | JSON-RPC over Streamable HTTP   | `LLMS_DOC` registered as `dash.mcp` resource  |
| Web crawlers          | Plain HTTPS, often no JS        | `/robots.txt`, `/sitemap.xml`, static HTML    |
| Paste-into-chat users | One-shot HTTP fetch             | `/llms.txt`, `/<page>/llms.txt` as markdown   |

2.0 dropped everything that overlapped Dash MCP: `/page.json`,
`/architecture.txt`, `/architecture.toon`, `/llms.toon`, the whole
`toon_generator.py`, `mark_important()`, `mark_component_hidden()`,
component-tree extraction. See `CHANGELOG.md` for the full list.

## Repository layout

```
dash-hook-my-ai/
├── .claude/               # Claude Code config (this folder)
│   ├── CLAUDE.md          # ← you are here
│   ├── settings.json      # permissions for build / test loops
│   ├── skills/            # invokable workflows
│   │   └── release/       # /release — sdist + wheel + verify
│   └── archive/           # historical 1.x docs, kept for reference
├── dash_improve_my_llms/  # the package
│   ├── __init__.py        # public API + backend dispatcher
│   ├── _flask_adapter.py  # backend adapters — thin wrappers
│   ├── _fastapi_adapter.py
│   ├── _quart_adapter.py
│   ├── _mcp_bridge.py     # dash.mcp resource registration
│   ├── handlers.py        # pure functions, framework-agnostic
│   ├── bot_detection.py
│   ├── html_generator.py  # crawler-facing static HTML
│   ├── robots_generator.py
│   └── sitemap_generator.py
├── pages/                 # demo app pages (each has LLMS_DOC)
│   ├── home.py
│   ├── audience_mcp.py        # /audiences/mcp-clients
│   ├── audience_crawlers.py   # /audiences/web-crawlers
│   ├── audience_llm_context.py # /audiences/llm-context
│   ├── analytics.py
│   ├── admin.py               # mark_hidden() demo
│   └── v200_features.py
├── tests/                 # pytest suite
│   ├── test_*.py          # 2.0 tests
│   └── legacy/            # stale 1.x tests, kept for reference
├── docs/
│   └── SKILLS.md          # user-facing skills guide (not a Claude skill!)
├── app.py                 # demo app entry point
├── pyproject.toml         # package metadata + extras
├── README.md
├── CHANGELOG.md
├── LICENSE
└── MANIFEST.in
```

## Common commands

| Task | Command |
|---|---|
| Run the demo app | `python app.py` then visit http://localhost:8959/ |
| Run tests | `pytest tests/ --tb=short` (skip `tests/legacy/`) |
| Run tests with coverage | `pytest tests/ --cov=dash_improve_my_llms` |
| Build sdist + wheel | `python -m build` |
| Verify a built wheel | install in a temp venv + import + check `__version__` |
| Boot-check without running | `python -c "import importlib.util as u; u.spec_from_file_location('app','app.py').loader.exec_module(u.module_from_spec(u.spec_from_file_location('app','app.py')))"` |

For build+publish, prefer the `/release` skill which encodes the
whole sequence.

## Conventions

- **Add a `LLMS_DOC = """..."""` to every new page module.** The
  package warns at startup naming pages without prose. Aim for
  300–2000 words, structured as: H1 title, blockquote tagline,
  "What this page does", "What the user can do", "What it does NOT do".
- **Public API additions go through `__init__.py`'s `__all__` list.**
  Symbols not in `__all__` are private — adapters import from
  `_flask_adapter`, `handlers`, etc. with underscore prefix.
- **Handlers stay pure.** Anything new that touches a request/response
  cycle belongs in an adapter, not in `handlers.py`. The pure-vs-IO
  split is what makes the multi-backend story work.
- **Markdown link checking before release.** Anything that references
  a route the package no longer serves (`/page.json`, `/llms.toon`,
  etc.) should be caught before publishing.

## Don't

- **Don't re-introduce TOON, page.json, architecture.txt.** 2.0
  explicitly narrows scope. If a use case needs structured
  component data, that's Dash MCP's job.
- **Don't add hard dependencies to `pyproject.toml`'s `dependencies` list.**
  Flask/FastAPI/Quart are extras (`[flask]`, `[fastapi]`, `[quart]`).
  The bare install only requires `dash`.
- **Don't suggest `mark_important()` or `mark_component_hidden()`.**
  They're deprecation no-ops in 2.0 and will be deleted in 2.1. The
  replacement is: write emphasis directly into the page's `LLMS_DOC`
  markdown.

## Reference

- `docs/SKILLS.md` — practical user guide, also written for AI
  coding assistants
- `CHANGELOG.md` — full release history; 2.0 section explains every
  break
- `.claude/archive/` — historical 1.x design docs, kept so we can
  trace why things changed

## Auto memory

This project's auto memory lives at
`~/.claude/projects/-Users-pip-PycharmProjects-dash-hook-my-ai/memory/`.
The `project-v2-rescope.md` entry there is the canonical record of
the 2.0 design decisions.
