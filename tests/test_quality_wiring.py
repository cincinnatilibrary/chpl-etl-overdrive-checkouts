# tests/test_quality_wiring.py
"""Smoke test: run() emits ingestion-quality validation rows (B5a wiring).

Models the fixture setup on test_app.py and the buffer/client pattern from
the circ-trans reference wiring.  The autouse `disable_telemetry` fixture
sets CHPL_TELEMETRY_DISABLED=1, so we override TelemetryClient.from_env
to inject a real buffer-backed client so the validation rows land somewhere
we can inspect.

The OverDrive extract writes raw JSON page files (page_NNNN.json) to the
output run dir, each containing a {"checkouts": [...]} list of raw records.
Quality checks run AGAINST THOSE RAW FETCHED RECORDS loaded into an
in-memory DuckDB view named `fetched_checkouts` — NOT against the lagging
silver dbt table `overdrive.checkouts`.  The [quality].table in
chimpy-tenant.toml is the bare view name `fetched_checkouts`; the key
column is the raw API field `checkoutId`.
"""
import pytest

import app
from chimpy_lake.telemetry.buffer import Buffer
from chimpy_lake.telemetry.client import TelemetryClient


@pytest.fixture
def buf(tmp_path):
    b = Buffer(tmp_path / "buf.sqlite")
    yield b
    b.close()


@pytest.fixture
def quality_client(buf):
    """A real buffer-backed TelemetryClient for inspecting quality events."""
    return TelemetryClient(
        buffer=buf,
        tenant="overdrive-checkouts",
        environment="test",
        producer="test/quality",
        host="testhost",
    )


def test_run_emits_quality_validations(
    monkeypatch, tmp_path, canonical_run_dir, buf, quality_client
):
    """After a successful run(), the core validation kinds must be present
    in the telemetry buffer under the _platform.validations target table.

    We override TelemetryClient.from_env to inject the buffer-backed client
    so run()'s internal `telemetry` variable is observable.
    CHPL_TELEMETRY_URL is unset so hub=None (degraded mode — no comparative
    baselines).  No watermark_column for OverDrive (vendor time-window
    pagination, no monotonic cursor).

    Correctness: the quality checks run against the RAW records this run
    just fetched (in-memory DuckDB view `fetched_checkouts` with
    key_column=checkoutId), NOT against the lagging silver dbt table.
    """
    monkeypatch.delenv("CHPL_TELEMETRY_URL", raising=False)
    monkeypatch.delenv("CHPL_TELEMETRY_DISABLED", raising=False)
    monkeypatch.setattr(TelemetryClient, "from_env", staticmethod(lambda: quality_client))

    # Use fixture mode — no API calls, no CLIENT_KEY required.
    monkeypatch.setenv("FIXTURE_DIR", str(canonical_run_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    # No _quality_con injection — run() must build its own in-memory DuckDB
    # from the written page files and create the `fetched_checkouts` view.
    rc = app.run()

    assert rc == 0

    kinds = {
        w.payload["kind"]
        for w in buf.pending(limit=50)
        if w.target_table == "_platform.validations"
    }
    # volume, key_not_null, key_unique — no watermark for overdrive
    assert {"volume", "key_not_null", "key_unique"} <= kinds

    # Also verify schema_audits were emitted (covers the fetched_checkouts view columns).
    schema_rows = [
        w for w in buf.pending(limit=50)
        if w.target_table == "_platform.schema_audits"
    ]
    assert schema_rows, "expected at least one schema_audits row"
