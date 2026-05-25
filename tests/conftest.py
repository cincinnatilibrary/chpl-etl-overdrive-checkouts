"""Shared pytest fixtures for the OverDrive ETL test suite.

The `fake_overdrive_api` fixture builds an httpx.MockTransport that serves
captured OverDrive Reports API responses from a fixture directory in sequence.
Pagination is request-counter driven (not URL-encoded), because httpx's
`params=` kwarg REPLACES the URL query string — encoding `?_page=N` into
`nextPageUrl` would be stripped on the next call, causing infinite re-fetch
of page 1.
"""
import json
from pathlib import Path
from typing import Callable

import httpx
import pytest


@pytest.fixture(autouse=True)
def disable_telemetry(monkeypatch):
    """Ensure tests never touch the real telemetry hub.

    TelemetryClient.from_env() respects CHPL_TELEMETRY_DISABLED=1 and
    returns a no-op client (matches circ-trans conftest pattern).
    """
    monkeypatch.setenv("CHPL_TELEMETRY_DISABLED", "1")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_fake_overdrive_handler(run_dir: Path) -> Callable[[httpx.Request], httpx.Response]:
    """Build a request handler that serves `run_dir/page_NNNN.json` in sequence.

    Stateful: each non-token request advances an internal counter and returns the
    next page. `nextPageUrl` is set to a non-empty sentinel for all but the last
    page (its actual value is irrelevant — the client only checks truthiness via
    `while next_url:` in app.py).

    The token endpoint (`/token`) is always answered with a stub access_token.
    The state is per-handler-instance, so a fresh `make_fake_overdrive_handler`
    call gives a fresh counter (no cross-test bleed when each test gets its own
    `fake_overdrive_api` fixture).
    """
    pages = sorted(run_dir.glob("page_*.json"))
    if not pages:
        raise FileNotFoundError(f"no page_*.json files in {run_dir}")

    # Closure-state: request counter (non-token requests only).
    state = {"served": 0}
    sentinel_next = "checkouts?continue=1"  # any non-empty string; content unused

    def handler(request: httpx.Request) -> httpx.Response:
        # OAuth token endpoint — return a stub.
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={"access_token": "fake-token", "token_type": "Bearer", "expires_in": 3600},
            )

        # Reports API — serve next fixture page in sequence.
        state["served"] += 1
        page_idx = state["served"]
        if page_idx > len(pages):
            return httpx.Response(404, json={"error": f"no page {page_idx}"})

        body = json.loads(pages[page_idx - 1].read_text())

        # Construct the response body with a rewritten nextPageUrl. Use dict(...)
        # rather than mutating body in place — keeps fixture data immutable if a
        # future optimization caches the parsed dict.
        if page_idx < len(pages):
            body = dict(body, nextPageUrl=sentinel_next)
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
