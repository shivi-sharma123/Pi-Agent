FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc curl && rm -rf /var/lib/apt/lists/*

COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library and install it
COPY shared /app/shared
RUN pip install -e /app/shared/

# Copy dashboard code
COPY dashboard/api /app/api
COPY dashboard/tests /app/tests

ENV PYTHONPATH=/app

EXPOSE 8010

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8010"]
