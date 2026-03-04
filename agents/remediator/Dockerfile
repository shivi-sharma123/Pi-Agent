FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY agents/remediator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library and install it
COPY shared /app/shared
RUN pip install -e /app/shared/
# Copy the runbooks + code
COPY agents/remediator/runbooks /app/runbooks
COPY agents/remediator/src /app/remediator

ENV PYTHONPATH=/app
ENV DOCKER_HOST=unix:///var/run/docker.sock

CMD ["python", "/app/remediator/main.py"]
