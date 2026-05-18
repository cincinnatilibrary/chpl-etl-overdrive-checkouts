import os
import json
import datetime
from pathlib import Path

from overdrive_client import OverDriveRESTClient  # your local module


def main():
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

    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    page_files = []
    page_index = 0

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
            file_path.write_bytes(src.read_bytes())
            page_files.append(file_name)
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
            file_path.write_bytes(response.content)
            page_files.append(file_name)

            print(f"Saved: {file_path}")
            next_url = response.json().get("nextPageUrl")

    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

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


if __name__ == "__main__":
    main()
