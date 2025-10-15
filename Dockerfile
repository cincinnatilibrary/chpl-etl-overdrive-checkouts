FROM python:3.11-slim

# System basics (optional but nice to have)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Requirements (httpx is needed by your client lib)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Your code
COPY overdrive_client.py app.py ./

# Where results will be written
VOLUME ["/data"]

# Default output dir inside the container (can override via env)
ENV OUTPUT_DIR=/data

CMD ["python", "app.py"]
