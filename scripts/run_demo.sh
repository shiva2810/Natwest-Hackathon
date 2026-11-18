#!/usr/bin/env bash
# Start the whole demo: API on :8000, Streamlit UI on :8501. Ctrl+C stops both.
#   ./scripts/run_demo.sh            resume saved state
#   ./scripts/run_demo.sh --fresh    reset to the planted scenario first (do this before going on stage)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin

if [[ "${1:-}" == "--fresh" ]]; then
  rm -f runs/state.json runs/audit.jsonl
  echo "reset: state and audit log cleared"
fi

$PY/uvicorn seam.api:app --host 127.0.0.1 --port 8765 --log-level warning &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT

for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8765/health >/dev/null && break
  sleep 0.3
done
curl -sf http://127.0.0.1:8765/health >/dev/null && echo "API up: http://127.0.0.1:8765/docs" \
  || echo "API failed to start - UI will run the engine in-process"

$PY/streamlit run ui/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
