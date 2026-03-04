FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (for building some python packages if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*



# Install specific observer dependencies
COPY agents/observer/requirements.txt ./agents/observer/
RUN pip install --no-cache-dir -r agents/observer/requirements.txt

# Copy source code
# We copy shared and agents to keep the import paths working (PYTHONPATH=/app)
COPY shared/ /app/shared/
RUN pip install -e /app/shared/

COPY agents/observer/src/ /app/agents/observer/src/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# The ENTRYPOINT is python main.py, and we expect CMD or env vars to specify the type
ENTRYPOINT ["python", "-m", "agents.observer.src.main"]
