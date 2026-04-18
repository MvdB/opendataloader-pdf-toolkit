#!/usr/bin/env bash
set -euo pipefail

mkdir -p "${INPUT_DIR:-/data/in}" "${OUTPUT_DIR:-/data/out}"

HYBRID_PID=""
# Spawn the hybrid backend iff OCR is on and no external URL was provided.
# Setting HYBRID_URL externally (e.g. via docker-compose sidecar) skips this.
if [[ "${ENABLE_OCR:-false}" == "true" && -z "${HYBRID_URL:-}" ]]; then
  echo "[entrypoint] starting opendataloader-pdf-hybrid on port ${HYBRID_PORT:-5002}"
  cmd=(opendataloader-pdf-hybrid --port "${HYBRID_PORT:-5002}" --force-ocr --ocr-lang "${OCR_LANG:-en}")
  if [[ "${HYBRID_FULL:-false}" == "true" ]]; then
    cmd+=(--enrich-picture-description)
  fi
  "${cmd[@]}" &
  HYBRID_PID=$!
  export HYBRID_URL="http://127.0.0.1:${HYBRID_PORT:-5002}"
fi

cleanup() {
  if [[ -n "${HYBRID_PID}" ]] && kill -0 "${HYBRID_PID}" 2>/dev/null; then
    kill -TERM "${HYBRID_PID}" 2>/dev/null || true
    wait "${HYBRID_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

exec uvicorn pdf_toolkit.web.app:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8080}"
