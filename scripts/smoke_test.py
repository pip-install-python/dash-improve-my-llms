#!/usr/bin/env python
"""
Boot a real Dash app against the installed Dash version and assert the
package's whole public surface still works.

Run this inside an environment that already has the Dash version under test
installed; it makes no attempt to manage environments itself. `scripts/
matrix.py` drives it across versions, and CI does the same thing with a
job matrix.

This complements the pytest suite rather than duplicating it. pytest runs
against one Dash version and asserts fine-grained behaviour; this asserts
the coarse "does it actually serve the right bytes" contract against every
supported version, including the ones where Dash's own API differs (4.1.0
has no pluggable backends at all, so FastAPI and Quart are unreachable
there — that is a supported configuration, not a failure).

Exit code 0 = every checked configuration passed.
"""

from __future__ import annotations

import argparse
import inspect
import sys
import traceback
from typing import List, Tuple

STUB = "This page contains interactive content that requires JavaScript"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0 Safari/537.36"

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[2m",
    "\033[0m",
)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def dash_supports_backends() -> bool:
    from dash import Dash

    return "backend" in inspect.signature(Dash.__init__).parameters


def available_backends() -> List[str]:
    backends = ["flask"]
    if not dash_supports_backends():
        return backends
    for name, module in (("fastapi", "fastapi"), ("quart", "quart")):
        try:
            __import__(module)
        except ImportError:
            continue
        backends.append(name)
    return backends


def build_app(backend: str):
    import dash
    from dash import Dash, html

    import dash_improve_my_llms as pkg

    pkg._state.page_metadata.clear()
    pkg._state.hidden_pages.clear()
    pkg._state.network = pkg.NetworkConfig()

    if hasattr(dash, "page_registry"):
        dash.page_registry.clear()

    kwargs = {"use_pages": True, "pages_folder": ""}
    if backend != "flask":
        kwargs["backend"] = backend

    app = Dash(__name__, **kwargs)
    app.title = "Smoke App"
    app._base_url = "https://smoke.example"

    dash.register_page("home", path="/", name="Home", layout=html.Div("home"))
    dash.register_page("guide", path="/guide", name="Guide", layout=html.Div("guide"))
    dash.register_page("admin", path="/admin", name="Admin", layout=html.Div("admin"))

    pkg.register_page_metadata(
        "/", name="Home", description="Landing.", llms_doc="# Home\n\nWelcome here."
    )
    pkg.register_page_metadata(
        "/guide",
        name="The Guide",
        description="How to use it.",
        llms_doc=(
            "# The Guide\n\nSee [home](/) first.\n\n"
            "- step one\n- step two\n\n```python\nx = 1\n```"
        ),
    )
    # The bug this suite guards against: a later prose-free registration
    # must not erase the llms_doc registered above.
    pkg.register_page_metadata("/guide", name="Smoke | The Guide")
    pkg.mark_hidden("/admin")

    pkg.register_network(
        name="Smoke network",
        hub_url="https://hub.example",
        peers=[{"name": "Sibling", "url": "https://sibling.example"}],
        external=[{"name": "Upstream", "url": "https://upstream.example"}],
    )

    app.layout = html.Div([dash.page_container])
    pkg.add_llms_routes(app, pkg.LLMSConfig(warn_missing_llms_doc=False))
    return app


def make_getter(app, backend: str):
    if backend == "fastapi":
        from starlette.testclient import TestClient

        # Entered as a context manager on purpose. Dash's FastAPI backend
        # registers its page catch-all route from the ASGI *lifespan* startup
        # event, and TestClient only runs lifespan when used this way. Without
        # it every non-root page 404s and the harness reports a routing bug
        # that does not exist under uvicorn.
        client = TestClient(app.server)
        client.__enter__()

        def get(path: str, ua: str = BROWSER) -> Tuple[int, str]:
            response = client.get(path, headers={"User-Agent": ua})
            return response.status_code, response.text

        return get

    if backend == "quart":
        import asyncio

        client = app.server.test_client()

        def get(path: str, ua: str = BROWSER) -> Tuple[int, str]:
            async def _run():
                response = await client.get(path, headers={"User-Agent": ua})
                return response.status_code, await response.get_data(as_text=True)

            return asyncio.new_event_loop().run_until_complete(_run())

        return get

    client = app.server.test_client()

    def get(path: str, ua: str = BROWSER) -> Tuple[int, str]:
        response = client.get(path, headers={"User-Agent": ua})
        return response.status_code, response.get_data(as_text=True)

    return get


def run_checks(get) -> None:
    # --- the core regression: prose reaches the crawler-facing body --------
    status, body = get("/guide", GOOGLEBOT)
    check(status == 200, f"/guide returned {status} to a crawler")
    check(STUB not in body, "/guide served the JavaScript stub to a crawler")
    check("<h1>The Guide</h1>" in body, "/guide body is missing its heading")
    check("<li>step one</li>" in body, "list items did not render")
    check('<a href="/">home</a>' in body, "prose link did not render as an anchor")
    check("<pre><code" in body, "fenced code did not render")

    # --- prose survives a later metadata refresh --------------------------
    check("Smoke | The Guide" in body, "the refreshed page name did not apply")

    # --- universal prerender ---------------------------------------------
    status, body = get("/guide", BROWSER)
    check(status == 200, f"/guide returned {status} to a browser")
    check('id="dimll-prerender"' in body, "prerender block missing for a browser")
    check("<h1>The Guide</h1>" in body, "prerendered body missing its heading")
    check("react-entry-point" in body, "Dash mount point was destroyed")
    check("<title>Smoke | The Guide</title>" in body, "per-page <title> not applied")
    check('rel="canonical"' in body, "canonical link missing")

    # --- pages are not near-duplicates ------------------------------------
    _, home = get("/", GOOGLEBOT)
    check("Welcome here." in home, "home prose missing")
    check(
        home.split("<main>")[1] != body.split("<main>")[1],
        "two pages rendered identical bodies",
    )

    # --- llms.txt ---------------------------------------------------------
    status, index = get("/llms.txt")
    check(status == 200, f"/llms.txt returned {status}")
    check("## Pages" in index, "/llms.txt is not an index")
    check("https://smoke.example/guide" in index, "/llms.txt missing a page URL")
    check("smoke.example//llms.txt" not in index, "/llms.txt has a double slash")
    check("## Network" in index, "/llms.txt missing the network section")
    check("https://sibling.example/llms.txt" in index, "peer llms.txt missing")

    status, page_doc = get("/guide/llms.txt")
    check(status == 200, f"/guide/llms.txt returned {status}")
    check(page_doc.startswith("# The Guide"), "/guide/llms.txt has the wrong body")
    check("<!DOCTYPE html>" not in page_doc, "an agent received HTML, not Markdown")

    # --- llms.txt navigation: a page document must not be a dead end -------
    check(
        "https://smoke.example/llms.txt" in page_doc,
        "/guide/llms.txt has no link to the site index",
    )
    check(
        "https://hub.example/llms.txt" in page_doc,
        "/guide/llms.txt has no link to the network index",
    )

    # --- the browser view is a different presentation, same document -------
    status, viewer = get("/guide/llms.txt?format=html")
    check(status == 200, f"/guide/llms.txt?format=html returned {status}")
    check("dv-banner" in viewer, "the llms.txt viewer did not render its banner")
    check("<h1>The Guide</h1>" in viewer, "the viewer did not render the document")
    check("noindex" in viewer, "the viewer is missing its noindex directive")

    # --- robots + sitemap -------------------------------------------------
    status, robots = get("/robots.txt")
    check(status == 200, f"/robots.txt returned {status}")
    check("Sitemap: https://smoke.example/sitemap.xml" in robots, "sitemap URL missing")

    status, sitemap = get("/sitemap.xml")
    check(status == 200, f"/sitemap.xml returned {status}")
    check("https://smoke.example/guide" in sitemap, "sitemap missing a page")

    # --- hidden pages stay hidden -----------------------------------------
    check(get("/admin", GOOGLEBOT)[0] == 404, "hidden page served to a crawler")
    check(get("/admin/llms.txt")[0] == 404, "hidden page's llms.txt was served")
    check("/admin" not in sitemap, "hidden page leaked into the sitemap")
    check("/admin" not in index, "hidden page leaked into /llms.txt")
    check('id="dimll-prerender"' not in get("/admin", BROWSER)[1], "hidden prerendered")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        action="append",
        choices=["flask", "fastapi", "quart"],
        help="Only test this backend (repeatable). Defaults to all available.",
    )
    args = parser.parse_args()

    import dash

    import dash_improve_my_llms as pkg

    backends = args.backend or available_backends()

    print(
        f"{DIM}dash {dash.__version__} · dash-improve-my-llms {pkg.__version__} · "
        f"python {sys.version.split()[0]}{RESET}"
    )
    if not dash_supports_backends():
        print(f"{YELLOW}  note: this Dash has no pluggable backends; " f"Flask only.{RESET}")

    failures = 0
    skipped = 0
    passed = 0
    xfailed = 0

    from dash_improve_my_llms._compat import find_known_issue

    for backend in backends:
        known_issue = find_known_issue(dash.__version__, backend)

        try:
            app = build_app(backend)
        except ImportError as exc:
            # Dash itself cannot provide this backend in this environment
            # (missing `dash[fastapi]`-style extras). That is an environment
            # gap, not a defect in this package — say so rather than
            # reporting a failure nobody can act on.
            skipped += 1
            print(f"  {YELLOW}SKIP{RESET} {backend}: {exc}")
            continue

        try:
            run_checks(make_getter(app, backend))
        except (SmokeFailure, Exception) as exc:  # noqa: BLE001
            if known_issue:
                xfailed += 1
                print(f"  {YELLOW}XFAIL{RESET} {backend}: known upstream issue")
                print(f"        {DIM}{known_issue}{RESET}")
                continue

            failures += 1
            if isinstance(exc, SmokeFailure):
                print(f"  {RED}FAIL{RESET} {backend}: {exc}")
            else:
                print(f"  {RED}ERROR{RESET} {backend}:")
                traceback.print_exc()
        else:
            if known_issue:
                # Upstream shipped a fix; stop claiming this is broken.
                print(
                    f"  {GREEN}PASS{RESET} {backend} "
                    f"{YELLOW}(expected to fail — remove it from "
                    f"KNOWN_UPSTREAM_ISSUES){RESET}"
                )
            else:
                print(f"  {GREEN}PASS{RESET} {backend}")
            passed += 1

    summary = f"{passed} passed"
    if xfailed:
        summary += f", {xfailed} xfailed"
    if skipped:
        summary += f", {skipped} skipped"
    if failures:
        print(f"{RED}{summary}, {failures} failed{RESET}")
        return 1

    print(f"{GREEN}{summary}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
