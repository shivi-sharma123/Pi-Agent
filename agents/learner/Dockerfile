FROM python:3.12-slim

# System deps needed for sentence-transformers / torch CPU-only
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install shared package first (layer-caching friendly)
COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared/

# Install agent dependencies
COPY agents/learner/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so the first startup is fast
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy agent source
COPY agents/learner/src/ /app/src/
WORKDIR /app/src

ENV PYTHONPATH="/app:/app/src"

CMD ["python", "main.py"]
