# CHPL OverDrive Checkouts ETL

This project downloads OverDrive Checkout data from the OverDrive REST API
and saves each API response as a serialized (pickled) file.
Each run stores results in a timestamped folder inside a mounted local volume.

The container is designed for scheduled or orchestrated ETL runs (e.g. with [Prefect](https://www.prefect.io/)).

---

## Project structure

```
.
├── app.py                 # Main ETL runner
├── overdrive_client.py    # Simple HTTPX-based OverDrive client
├── Dockerfile             # Build definition (Python 3.11 base)
├── docker-compose.yml     # Local runtime setup
├── requirements.txt       # Python dependencies
└── .env.example           # Template for environment variables
```

---

## ⚙️ Environment variables

`CLIENT_KEY` OverDrive client key
`CLIENT_SECRET` OverDrive client secret
`WEBSITE_ID` Optional OverDrive website ID 
`USER_AGENT` Optional Custom user agent string |
`OUTPUT_DIR` Optional Path inside container for output (`/data`)

Example `.env` file:

```bash
CLIENT_KEY=YOUR_KEY
CLIENT_SECRET=YOUR_SECRET
WEBSITE_ID=47
USER_AGENT=CHPL-OverDriveClient/1.0 (Cincinnati & Hamilton County Public Library; contact: ray.voelker@chpl.org)
```

> ⚠️ **Do not commit your real `.env`** — use `.env.example` for sharing variable names.

---

## Quickstart

### 1. Clone the repo

```bash
git clone git@github.com:cincinnatilibrary/chpl-etl-overdrive-checkouts.git
cd chpl-etl-overdrive-checkouts
```

### 2. Create your `.env`

Copy the template and fill in secrets:

```bash
cp .env.example .env
```

### 3. Build the container

```bash
docker compose build
```

### 4. Run the ETL

```bash
docker compose up
```

The container will:
1. Fetch OverDrive checkouts for the last two days
2. Save responses as `.pkl` files inside `/data/overdrive_YYYYMMDD_HHMMSS`
3. Mount those files locally to `./out` on the host

### 5. View results

Pickle data is saved under:

```
out/overdrive_YYYYMMDD_HHMMSS/
├── response_1697412280.pkl
├── response_1697412295.pkl
└── ...
```

You can inspect any file in Python:

```python
import pickle
with open("out/overdrive_20251015_130000/response_1697412280.pkl", "rb") as f:
    data = pickle.load(f)
```

---

## Cleanup

Remove all containers and build cache:

```bash
docker compose down --rmi local --volumes
```

---

## Future integration

This image is Prefect-ready — once validated, it can be wrapped in a Prefect flow
to automate daily/weekly ETL jobs and monitor their status.

---

Cincinnati & Hamilton County Public Library
