"""Characterization tests for app.main().

We patch OverDriveRESTClient so the orchestration uses the fake API, point
OUTPUT_DIR at a tmp dir, and assert the output shape (page_NNNN.json files
+ run.json manifest).
"""
import json
from pathlib import Path

import httpx
import pytest

import app
import overdrive_client


@pytest.fixture
def patched_client(monkeypatch, fake_overdrive_api):
    """Patch OverDriveRESTClient.__init__ to inject the fake transport."""
    original_init = overdrive_client.OverDriveRESTClient.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._client = httpx.Client(transport=fake_overdrive_api, base_url=self.base_url)

    monkeypatch.setattr(overdrive_client.OverDriveRESTClient, "__init__", patched_init)


@pytest.fixture
def app_env(monkeypatch, tmp_path):
    """Set the env vars app.main() expects, pointing OUTPUT_DIR at a tmp dir."""
    monkeypatch.setenv("CLIENT_KEY", "fake_key")
    monkeypatch.setenv("CLIENT_SECRET", "fake_secret")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    return tmp_path


def test_main_writes_one_json_per_fixture_page(patched_client, app_env, canonical_run_dir):
    """app.main() should produce one page_NNNN.json per fixture page + run.json manifest."""
    app.main()

    # There should be exactly one new overdrive_<ts>/ subdir under OUTPUT_DIR
    subdirs = [p for p in app_env.iterdir() if p.is_dir() and p.name.startswith("overdrive_")]
    assert len(subdirs) == 1, f"expected one run dir, found: {subdirs}"
    run_dir = subdirs[0]

    n_expected = len(list(canonical_run_dir.glob("page_*.json")))
    pages = sorted(run_dir.glob("page_*.json"))
    assert len(pages) == n_expected
    manifest = run_dir / "run.json"
    assert manifest.exists()


def test_main_manifest_has_expected_fields(patched_client, app_env, canonical_run_dir):
    app.main()
    run_dir = next(p for p in app_env.iterdir() if p.is_dir() and p.name.startswith("overdrive_"))
    manifest = json.loads((run_dir / "run.json").read_text())
    expected_keys = {
        "run_id", "source", "stage", "status",
        "window_start", "window_end",
        "page_count", "pages",
        "started_at", "finished_at",
    }
    assert set(manifest.keys()) == expected_keys
    assert manifest["source"] == "overdrive"
    assert manifest["stage"] == "extract"
    assert manifest["status"] == "completed"
    n_expected = len(list(canonical_run_dir.glob("page_*.json")))
    assert manifest["page_count"] == n_expected
    assert len(manifest["pages"]) == n_expected


def test_main_writes_page_files_as_raw_bytes(patched_client, app_env):
    """The page files should be valid JSON (the orchestration writes response.content)."""
    app.main()
    run_dir = next(p for p in app_env.iterdir() if p.is_dir() and p.name.startswith("overdrive_"))
    for page in sorted(run_dir.glob("page_*.json")):
        body = json.loads(page.read_text())
        assert "checkouts" in body


def test_main_does_not_write_manifest_on_mid_run_failure(monkeypatch, app_env, canonical_run_dir):
    """If a page request fails partway, run.json should NOT be written.

    Per app.py: manifest is written only after the request loop completes successfully.
    """
    from itertools import count
    attempts = count(1)
    n_total = len(list(canonical_run_dir.glob("page_*.json")))

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(
                200, json={"access_token": "t", "token_type": "Bearer", "expires_in": 3600}
            )
        n = next(attempts)
        # Succeed for first page, fail with 400 on second
        if n == 1:
            return httpx.Response(
                200, json={"checkouts": [], "nextPageUrl": "checkouts?_page=2"}
            )
        return httpx.Response(400, json={"error": "simulated mid-run failure"})

    # Skip this test if the fixture is single-page (would not exercise mid-run failure)
    if n_total < 2:
        pytest.skip("fixture is single-page; mid-run failure not exercisable")

    original_init = overdrive_client.OverDriveRESTClient.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._client = httpx.Client(
            transport=httpx.MockTransport(failing_handler), base_url=self.base_url
        )

    monkeypatch.setattr(overdrive_client.OverDriveRESTClient, "__init__", patched_init)

    with pytest.raises(httpx.HTTPStatusError):
        app.main()

    # The run dir was created and at least one page written, but NO run.json
    subdirs = [p for p in app_env.iterdir() if p.is_dir() and p.name.startswith("overdrive_")]
    assert len(subdirs) == 1
    assert not (subdirs[0] / "run.json").exists()


def test_main_reads_from_fixture_dir_when_env_set(monkeypatch, tmp_path, canonical_run_dir):
    """When FIXTURE_DIR is set, app.main() reads pages from there instead of calling the API.

    No CLIENT_KEY/SECRET needed in this mode (and a sentinel value should not trigger
    any HTTP call). Output mirrors the fixture's page count and produces a manifest.
    """
    monkeypatch.setenv("FIXTURE_DIR", str(canonical_run_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    # Deliberately NOT setting CLIENT_KEY/SECRET — fixture mode should not require them.

    app.main()

    subdirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("overdrive_")]
    assert len(subdirs) == 1
    run_dir = subdirs[0]

    n_expected = len(list(canonical_run_dir.glob("page_*.json")))
    pages = sorted(run_dir.glob("page_*.json"))
    assert len(pages) == n_expected

    manifest = json.loads((run_dir / "run.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["page_count"] == n_expected
    # Source/stage stay the same; the only difference is the data path.
    assert manifest["source"] == "overdrive"
    assert manifest["stage"] == "extract"
