FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY agents/orchestrator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library and install it
COPY shared /app/shared
RUN pip install -e /app/shared/

# Copy orchestrator code
COPY agents/orchestrator/src /app/orchestrator

ENV PYTHONPATH=/app

CMD ["python", "/app/orchestrator/main.py"]
