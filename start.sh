#!/usr/bin/env bash
# Double-click-style launcher for Linux/Mac: first run sets up a virtual
# environment and installs dependencies, every run after that starts
# instantly. Opens your browser to the app automatically.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

PORT="${PORT:-8000}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found."
  echo "Install it from https://www.python.org/downloads/ and run this script again."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "First-time setup: creating a virtual environment..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if command -v sha256sum >/dev/null 2>&1; then
  NEW_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
else
  NEW_HASH="$(shasum -a 256 requirements.txt | cut -d' ' -f1)"
fi
REQ_HASH_FILE=".venv/.requirements.sha256"
OLD_HASH="$(cat "$REQ_HASH_FILE" 2>/dev/null || true)"

if [ "$NEW_HASH" != "$OLD_HASH" ]; then
  PIP_INDEX="${COLLECTION_DATA_PIP_INDEX_URL:-https://pypi.org/simple}"
  echo "Installing dependencies (first run only, this can take a minute)..."
  echo "Using package index: $PIP_INDEX"
  if ! pip install --quiet --no-cache-dir --index-url "$PIP_INDEX" --upgrade pip \
      || ! pip install --quiet --no-cache-dir --index-url "$PIP_INDEX" -r requirements.txt; then
    echo ""
    echo "Could not install dependencies -- see the error above."
    echo "This usually means pip resolved an outdated or broken package index (for"
    echo "example, a stale corporate mirror). The default index above is the real"
    echo "pypi.org, which should have everything needed. If your network requires a"
    echo "private mirror instead, set COLLECTION_DATA_PIP_INDEX_URL to it and rerun."
    exit 1
  fi
  echo "$NEW_HASH" > "$REQ_HASH_FILE"
fi

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo ""
echo "Starting Collection Data on http://localhost:$PORT ..."
echo "(Press Ctrl+C to stop)"
echo ""
uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

READY=""
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT"; then
    READY=1
    break
  fi
  sleep 0.5
done

URL="http://localhost:$PORT"
if [ -n "$READY" ]; then
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 &
  else
    echo "Open your browser to $URL"
  fi
fi

wait "$SERVER_PID"
