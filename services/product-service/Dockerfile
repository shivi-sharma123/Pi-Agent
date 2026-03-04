# Product Service — Django REST + Gunicorn
FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=false \
    PORT=8003 \
    GUNICORN_WORKERS=2

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -sf http://localhost:8003/health || exit 1

CMD ["python", "-m", "app.main"]
