FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Ensure pip is up to date
RUN pip install --upgrade pip

# Copy shared package
COPY shared /app/shared/
RUN pip install -e "shared/"

# Install diagnoser dependencies
COPY agents/diagnoser/requirements.txt /app/agents/diagnoser/
RUN pip install -r /app/agents/diagnoser/requirements.txt

# Copy diagnoser source
COPY agents/diagnoser/src /app/agents/diagnoser/src/

# Run as non-root
RUN useradd -m agentuser
USER agentuser

ENV PYTHONPATH=/app

CMD ["python", "agents/diagnoser/src/main.py"]
