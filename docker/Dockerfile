# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --upgrade pip && pip install ".[ocr,enrich,auth,redis]"

FROM python:3.13-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INPUT_DIR=/data/in \
    OUTPUT_DIR=/data/out \
    HOST=0.0.0.0 \
    PORT=8080 \
    PROFILE=rag \
    SANITIZE=true \
    ENABLE_OCR=false \
    HYBRID_FULL=false \
    OCR_LANG=en \
    HYBRID_PORT=5002

RUN apt-get update \
 && apt-get install -y --no-install-recommends default-jre-headless tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && mkdir -p /data/in /data/out

VOLUME ["/data/in", "/data/out"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + str(__import__('os').environ.get('PORT','8080')) + '/health', timeout=3)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
