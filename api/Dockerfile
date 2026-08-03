# Build from the REPO ROOT so `api` is importable as a package:
#   docker build -f api/Dockerfile -t ghostkube/api:dev .
#
# Stage 1: Build
FROM python:3.13-slim as builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim
WORKDIR /app

# Install system dependencies for Playwright (Crawl4AI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 \
    && (apt-get install -y --no-install-recommends libasound2 \
        || apt-get install -y --no-install-recommends libasound2t64) \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser

# Set ownership during the copy, not afterwards. A `RUN chown -R` over this tree
# rewrites every file into a new layer - it holds torch, transformers and scipy,
# so that is >1GB copied twice and several minutes of build time on Docker
# Desktop. `COPY --chown` does the same job in one pass.
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
COPY --chown=appuser:appuser . .

ENV PATH=/home/appuser/.local/bin:$PATH

USER appuser

# Playwright must be installed AS appuser, after the USER switch. The deps live
# in /home/appuser/.local, which is not on root's sys.path, so running this as
# root fails with "No module named playwright" - ENV PATH fixes executable
# lookup, not module imports. Running it here also puts the browser in
# appuser's own cache, which is the user that needs it at runtime.
RUN python -m playwright install chromium

# Bake the embedding model weights into the image so a cold pod never needs
# egress to Hugging Face on startup (see api/config.py EMBED_MODEL_NAME).
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L12-v2')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]