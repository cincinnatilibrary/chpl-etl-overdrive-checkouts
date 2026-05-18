"""Shared pytest fixtures for the OverDrive ETL test suite.

The `fake_overdrive_api` fixture builds an httpx.MockTransport that serves
captured OverDrive Reports API responses from a fixture directory. Pagination
is wired up via the `nextPageUrl` field — the fake handler computes which
page-file to serve based on the request URL.
"""
import json
from pathlib import Path
from typing import Callable

import httpx
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _page_index_from_url(url: httpx.URL, default: int = 1) -> int:
    """Extract the page index from a fake-paginated URL.

    The fake API encodes the next page index in the query string as
    `?_page=N`. The first request (no `_page` param) is treated as page 1.
    """
    val = url.params.get("_page")
    return int(val) if val is not None else default


def make_fake_overdrive_handler(run_dir: Path) -> Callable[[httpx.Request], httpx.Response]:
    """Build a request handler that serves `run_dir/page_NNNN.json` with pagination.

    `nextPageUrl` in each served page is rewritten to use the fake's
    `?_page=N+1` scheme so the client follows pagination through the fixture.
    The token endpoint (`/token`) is always answered with a stub access_token.
    """
    pages = sorted(run_dir.glob("page_*.json"))
    if not pages:
        raise FileNotFoundError(f"no page_*.json files in {run_dir}")

    def handler(request: httpx.Request) -> httpx.Response:
        # OAuth token endpoint — return a stub
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={"access_token": "fake-token", "token_type": "Bearer", "expires_in": 3600},
            )

        # Reports API — serve from fixture dir, rewriting nextPageUrl
        page_idx = _page_index_from_url(request.url, default=1)
        if page_idx > len(pages):
            return httpx.Response(404, json={"error": f"no page {page_idx}"})

        page_path = pages[page_idx - 1]
        body = json.loads(page_path.read_text())

        # Construct the response body with a rewritten nextPageUrl. Use dict(...) rather
        # than mutating body in place — keeps fixture data immutable if a future
        # optimization caches the parsed dict.
        if page_idx < len(pages):
            body = dict(body, nextPageUrl=f"checkouts?_page={page_idx + 1}")
        else:
            body = dict(body, nextPageUrl=None)

        return httpx.Response(200, json=body)

    return handler


@pytest.fixture
def fixtures_root():
    """Path to the tests/fixtures/ directory."""
    return FIXTURES_DIR


@pytest.fixture
def canonical_run_dir(fixtures_root):
    """Path to the first captured prod fixture (oldest by name → oldest by timestamp,
    since run dirs are named `overdrive_<YYYYMMDD_HHMMSS>`).

    Oldest-as-canonical keeps test behavior stable as new fixtures accumulate.
    Tests that need a *specific* run dir should request it directly, not via
    this fixture.
    """
    candidates = sorted(p for p in fixtures_root.glob("overdrive_*") if p.is_dir())
    if not candidates:
        pytest.skip(
            f"no fixture run dirs under {fixtures_root} — "
            f"run scripts/capture-fixture.sh to populate (requires ai-vault unlocked)"
        )
    return candidates[0]


@pytest.fixture
def fake_overdrive_api(canonical_run_dir):
    """An httpx.MockTransport that serves the canonical fixture run."""
    return httpx.MockTransport(make_fake_overdrive_handler(canonical_run_dir))
