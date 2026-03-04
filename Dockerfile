FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY any_gateway/ ./any_gateway/
COPY apps/ ./apps/

ENV PYTHONPATH=/app/any_gateway

EXPOSE 8002 8502

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "any_gateway/main.py"]
