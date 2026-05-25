import sys
import os
import json
import datetime
from pathlib import Path

from overdrive_client import OverDriveRESTClient  # your local module
from chimpy_lake.telemetry import TelemetryClient


def run(args=None) -> int:
    # --- env vars ---
    fixture_dir = os.environ.get("FIXTURE_DIR")
    base_output_dir = Path(os.environ.get("OUTPUT_DIR", "/data"))
    user_agent = os.environ.get(
        "USER_AGENT",
        "CHPL-OverDriveClient/1.0 (Cincinnati & Hamilton County Public Library; contact: ray.voelker@chpl.org)",
    )

    if fixture_dir is None:
        # Real-API mode — require credentials.
        client_key = os.environ["CLIENT_KEY"]
        client_secret = os.environ["CLIENT_SECRET"]
        website_id = os.environ.get("WEBSITE_ID", "47")

        client = OverDriveRESTClient(
            client_key=client_key,
            client_secret=client_secret,
            default_headers={
                "websiteId": website_id,
                "User-Agent": user_agent,
            },
        )

    # --- date range ---
    today = datetime.date.today()
    endDateUtc = today
    startDateUtc = today - datetime.timedelta(days=2)
    print(f"Date range: {startDateUtc} → {endDateUtc}  (fixture_dir={fixture_dir!r})")

    params = {
        "startDateUtc": str(startDateUtc),
        "endDateUtc": str(endDateUtc),
    }

    # --- timestamped output dir ---
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"overdrive_{timestamp}"
    output_dir = base_output_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- telemetry setup (outside the run context; idempotent) ---
    telemetry = TelemetryClient.from_env()
    telemetry.register_source(
        description="OverDrive checkouts extract (REST → run.json pages)",
        slo_max_age_hours=26,
    )
    triggered_by = os.environ.get("CHPL_TRIGGERED_BY", "scheduled")

    with telemetry.run(triggered_by=triggered_by) as run:
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

        page_files = []
        page_index = 0
        record_count = 0

        if fixture_dir is not None:
            # Fixture mode — copy pages from FIXTURE_DIR (no API calls).
            # This is the local dev / CI path; production never sets FIXTURE_DIR.
            fixture_pages = sorted(Path(fixture_dir).glob("page_*.json"))
            if not fixture_pages:
                raise FileNotFoundError(f"no page_*.json files in FIXTURE_DIR={fixture_dir}")
            for src in fixture_pages:
                page_index += 1
                file_name = f"page_{page_index:04d}.json"
                file_path = output_dir / file_name
                raw = src.read_bytes()
                if not os.environ.get("CHPL_DRY_RUN"):
                    file_path.write_bytes(raw)
                page_files.append(file_name)
                # Count checkouts records from the page body (best-effort; 0 on parse failure).
                try:
                    record_count += len(json.loads(raw).get("checkouts", []))
                except Exception:
                    pass
                if not os.environ.get("CHPL_DRY_RUN"):
                    print(f"Saved (from fixture): {file_path}")
        else:
            # Real-API mode — fetch + paginate.
            next_url = "checkouts"
            while next_url:
                page_index += 1
                response = client.request("GET", next_url, params=params)
                response.raise_for_status()

                file_name = f"page_{page_index:04d}.json"
                file_path = output_dir / file_name
                if not os.environ.get("CHPL_DRY_RUN"):
                    file_path.write_bytes(response.content)
                page_files.append(file_name)

                # Count checkouts records from the page body (best-effort; 0 on parse failure).
                try:
                    record_count += len(response.json().get("checkouts", []))
                except Exception:
                    pass

                if not os.environ.get("CHPL_DRY_RUN"):
                    print(f"Saved: {file_path}")
                next_url = response.json().get("nextPageUrl")

        finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

        # Set telemetry attributes from the actual results.
        run.record_count = record_count
        run.page_count = page_index

        if os.environ.get("CHPL_DRY_RUN"):
            print(
                f"[dry-run] fetched {page_index} pages from OverDrive; "
                f"counted {record_count} records; "
                f"skipped page writes and run.json manifest",
                file=sys.stderr,
            )
            return 0

        # CRITICAL: run.json write is INSIDE the with-block to preserve the atomicity
        # invariant: a mid-run fetch exception leaves no manifest.
        manifest = {
            "run_id": run_id,
            "source": "overdrive",
            "stage": "extract",
            "status": "completed",
            "window_start": str(startDateUtc),
            "window_end": str(endDateUtc),
            "page_count": page_index,
            "pages": page_files,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        manifest_path = output_dir / "run.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

        print(f"Saved {page_index} pages to '{output_dir}'")
        print(f"Manifest: {manifest_path}")

    return 0


if __name__ == "__main__":
    from chimpy_lake.lifecycle import LifecycleApp
    LifecycleApp(run=run).main()
