# Multi-stage build: Frontend (Node.js) + Backend (Python)

# Stage 1: Build frontend React/Tailwind
FROM node:22-alpine as frontend-builder

WORKDIR /app/frontend

# Copy frontend files
COPY frontend/package.json frontend/pnpm-lock.yaml ./
COPY frontend/patches ./patches
COPY frontend/client ./client
COPY frontend/server ./server
COPY frontend/tsconfig.json frontend/vite.config.ts ./

# Install dependencies and build
RUN npm install -g pnpm && \
    pnpm install --frozen-lockfile && \
    pnpm run build

# Stage 2: Python backend with built frontend
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies. libgomp1 (OpenMP runtime) is required by
# onnxruntime, which piper-tts (backend/piper_tts.py) uses for inference —
# without it, `from piper import PiperVoice` fails at import/load time with
# "libgomp.so.1: cannot open shared object file", which the surrounding
# try/except swallows and reports as "no audio available" instead of the
# real cause. python:3.12-slim doesn't ship it by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ backend/
COPY public/ public/

# Copy built frontend from builder stage
COPY --from=frontend-builder /app/frontend/dist/public ./frontend_dist

# Create non-root user
RUN useradd --system --create-home --uid 10001 lingua && \
    mkdir -p /app/data && \
    chown -R lingua:lingua /app

USER lingua

ENV PYTHONUNBUFFERED=1
ENV LINGUA_PORT=8100
ENV LINGUA_DB_PATH=/app/data/lingua.db
ENV LINGUA_CACHE_DIR=/app/data/media_cache

EXPOSE 8100

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8100/api/health || exit 1

CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8100"]
