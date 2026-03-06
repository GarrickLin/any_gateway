# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY apps/react/package*.json ./
RUN npm ci
COPY apps/react/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY any_gateway/ ./any_gateway/
COPY apps/ ./apps/
# Override source files with production build output
COPY --from=frontend-builder /frontend/dist ./apps/react/dist

ENV PYTHONPATH=/app/any_gateway

EXPOSE 8003

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser
USER appuser

CMD ["python", "-m", "uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8003", "--app-dir", "any_gateway"]
