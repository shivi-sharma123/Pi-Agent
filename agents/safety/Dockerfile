FROM python:3.11-slim

WORKDIR /app

# Core system deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

# Install specific agent dependencies
COPY agents/safety/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library and install it
COPY shared /app/shared
RUN pip install -e /app/shared/

# Copy agent code
COPY agents/safety/src /app/safety

ENV PYTHONPATH=/app

CMD ["python", "/app/safety/main.py"]
