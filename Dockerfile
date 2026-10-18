# ─── Build stage ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Production stage ────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Security: Install runtime curl for healthcheck only, then cleanup
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Security: Run as unprivileged user (UID 1000)
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY --chown=appuser:appgroup . .

# Create logs directory with user permissions
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app/logs

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PORT=8501

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -f http://127.0.0.1:${PORT}/_stcore/health || exit 1

CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT} --server.address=127.0.0.1 --server.headless=true --browser.gatherUsageStats=false"]
