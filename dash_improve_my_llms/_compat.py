"""
Known-bad Dash/backend combinations, and the startup check that reports them.

Every entry here has been reproduced against a **stock** Dash app with this
package uninstalled. Nothing in this file works around an upstream defect —
it only makes one visible, because the failure modes are quiet enough to
reach production unnoticed.

Why the package says anything at all about Dash's own bugs: an app on a
broken combination serves 500s or 404s on its deep page URLs while its home
page looks perfect. The symptom a maintainer sees is "our SEO collapsed",
and the cause is several layers below where they will look. One startup
warning naming the exact version and backend saves that hunt.
"""

from __future__ import annotations

import logging
import warnings
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# (dash_version, backend) -> explanation
KNOWN_UPSTREAM_ISSUES: Dict[Tuple[str, str], str] = {
    ("4.3.0", "fastapi"): (
        "Dash 4.3.0's FastAPI backend registers its page catch-all without "
        "calling set_current_request(), so every non-root page URL raises "
        "RuntimeError('No active request in context') and returns a 500. "
        "This reproduces on a stock Dash app with this package uninstalled, "
        "and is fixed in Dash 4.4.0. Crawlers hitting deep URLs will see "
        "server errors. Upgrade to dash>=4.4.0, or run the Flask or Quart "
        "backend on 4.3.0."
    ),
}

# Dash gained pluggable backends after 4.1; on 4.1.0 `Dash(backend=...)`
# does not exist and Flask is the only option.
FLASK_ONLY_VERSIONS = ("4.1.0",)


def find_known_issue(dash_version: str, backend: str) -> Optional[str]:
    """Return an explanation if this combination is known broken upstream."""
    return KNOWN_UPSTREAM_ISSUES.get((dash_version, backend))


def warn_on_known_issues(backend: str) -> Optional[str]:
    """
    Emit a warning if the running Dash/backend pair is known broken.

    Returns the message that was warned about, or None. Never raises — a
    diagnostic must not be able to take down the app it is diagnosing.
    """
    try:
        import dash

        version = getattr(dash, "__version__", "")
    except Exception:  # pragma: no cover - dash is a hard dependency
        return None

    message = find_known_issue(version, backend)
    if message is None:
        return None

    warnings.warn(
        f"dash-improve-my-llms: running on a Dash/backend combination with a "
        f"known upstream defect (dash {version} + {backend}). {message}",
        RuntimeWarning,
        stacklevel=3,
    )
    return message
