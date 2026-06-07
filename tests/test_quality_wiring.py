# tests/test_quality_wiring.py
"""Smoke test: run() emits ingestion-quality validation rows (B5a wiring).

Models the fixture setup on test_app.py and the buffer/client pattern from
the circ-trans reference wiring.  The autouse `disable_telemetry` fixture
sets CHPL_TELEMETRY_DISABLED=1, so we override TelemetryClient.from_env
to inject a real buffer-backed client so the validation rows land somewhere
we can inspect.

The OverDrive extract is extract-only (no DuckDB load in app.py), so we
inject a pre-seeded in-memory DuckDB connection via the `_quality_con`
parameter added to run() for testability.  Production uses a degradable
lake connection from env.
"""
import duckdb
import pytest

import app
from chimpy_lake.telemetry.buffer import Buffer
from chimpy_lake.telemetry.client import TelemetryClient


def _make_lake_con():
    """Return an in-memory DuckDB pre-seeded with overdrive.checkouts rows.

    Schema mirrors the silver dbt model (checkouts.sql) — only the columns
    needed for the quality validators are required here.
    """
    con = duckdb.connect()
    con.execute("CREATE SCHEMA overdrive")
    con.execute("""
        CREATE TABLE overdrive.checkouts (
            checkout_id    VARCHAR NOT NULL,
            checkout_date_utc TIMESTAMP,
            is_renewal     BOOLEAN,
            user_id        VARCHAR,
            title_id       BIGINT,
            title          VARCHAR,
            format         VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO overdrive.checkouts VALUES
            ('ck-001', '2026-01-01 10:00:00', false, 'u1', 1001, 'Book A', 'ebook'),
            ('ck-002', '2026-01-02 11:00:00', false, 'u2', 1002, 'Book B', 'audiobook'),
            ('ck-003', '2026-01-03 12:00:00', true,  'u3', 1001, 'Book A', 'ebook')
    """)
    return con


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
    """
    monkeypatch.delenv("CHPL_TELEMETRY_URL", raising=False)
    monkeypatch.delenv("CHPL_TELEMETRY_DISABLED", raising=False)
    monkeypatch.setattr(TelemetryClient, "from_env", staticmethod(lambda: quality_client))

    # Use fixture mode — no API calls, no CLIENT_KEY required.
    monkeypatch.setenv("FIXTURE_DIR", str(canonical_run_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    lake_con = _make_lake_con()
    rc = app.run(_quality_con=lake_con)
    lake_con.close()

    assert rc == 0

    kinds = {
        w.payload["kind"]
        for w in buf.pending(limit=50)
        if w.target_table == "_platform.validations"
    }
    assert {"volume", "key_not_null", "key_unique"} <= kinds   # no watermark for overdrive
