import os
import time
import pickle
import datetime
from pathlib import Path

from overdrive_client import OverDriveRESTClient  # your local module

def main():
    # --- env vars ---
    client_key = os.environ["CLIENT_KEY"]
    client_secret = os.environ["CLIENT_SECRET"]
    website_id = os.environ.get("WEBSITE_ID", "47")
    user_agent = os.environ.get(
        "USER_AGENT",
        "CHPL-OverDriveClient/1.0 (Cincinnati & Hamilton County Public Library; contact: ray.voelker@chpl.org)",
    )
    base_output_dir = Path(os.environ.get("OUTPUT_DIR", "/data"))

    # --- date range ---
    today = datetime.date.today()
    endDateUtc = today
    startDateUtc = today - datetime.timedelta(days=2)
    print(f"Date range: {startDateUtc} → {endDateUtc}")

    # --- client ---
    client = OverDriveRESTClient(
        client_key=client_key,
        client_secret=client_secret,
        default_headers={
            "websiteId": website_id,
            "User-Agent": user_agent,
        },
    )

    params = {
        "startDateUtc": str(startDateUtc),
        "endDateUtc": str(endDateUtc),
    }

    # --- timestamped output dir under /data ---
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_output_dir / f"overdrive_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- request loop ---
    next_url = "checkouts"
    file_names = []

    while next_url:
        response = client.request("GET", next_url, params=params)

        file_path = output_dir / f"response_{int(time.time())}.pkl"
        file_names.append(str(file_path))

        with open(file_path, "wb") as f:
            pickle.dump(response, f)

        print(f"Saved: {file_path}")

        # follow pagination
        next_url = response.json().get("nextPageUrl")

    print(f"Saved {len(file_names)} responses to '{output_dir}'")

if __name__ == "__main__":
    main()
