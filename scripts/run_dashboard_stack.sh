#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
DASHBOARD_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
SITE_DIR="$DASHBOARD_ROOT/site"
TRACKER_DIR="$DASHBOARD_ROOT/tracker"
RUNTIME_DIR="$DASHBOARD_ROOT/runtime"
PRESIGN_TOOL="$SCRIPT_DIR/generate_r2_presigned_put.py"

TARGET_ROOT="${1:-${TARGET_ROOT:-/mnt/f/_evolve/turnloop}}"
PORT="${PORT:-4173}"
TARGET_NAME="$(basename "$TARGET_ROOT")"
if [ "$TARGET_NAME" = "git-build" ]; then
  DEFAULT_RUN_ID="livestream-git-build"
else
  DEFAULT_RUN_ID="${TARGET_NAME}-run"
fi
RUN_ID="${RUN_ID:-$DEFAULT_RUN_ID}"
RESEARCH_LOG="${RESEARCH_LOG:-$TARGET_ROOT/research.log}"
ORCHESTRATE_LOG="${ORCHESTRATE_LOG:-$TARGET_ROOT/orchestrate.log}"
DASHBOARD_LOG="$RUNTIME_DIR/dashboard.log"
STATE_JSON="$SITE_DIR/dist/state/live-state.json"
HTTP_LOG="$RUNTIME_DIR/http-server.log"
AGG_LOG="$RUNTIME_DIR/log-aggregator.log"
SYNC_LOG="$RUNTIME_DIR/state-sync.log"
R2_UPLOAD_URL="${R2_ENDPOINT:-}"
R2_PUBLIC_URL="${R2_PUBLIC_URL:-}"
TRACKER_TZ="${TRACKER_TZ:-Pacific/Honolulu}"
MILLRACE_WORKSPACE="${MILLRACE_WORKSPACE:-}"
PRODUCT_REPO="${PRODUCT_REPO:-}"

if [ -z "$MILLRACE_WORKSPACE" ] && [ -d "$TARGET_ROOT/millrace-agents" ]; then
  MILLRACE_WORKSPACE="$TARGET_ROOT"
fi

if [ -z "$PRODUCT_REPO" ]; then
  if [ -d "$TARGET_ROOT/auto-games/.git" ]; then
    PRODUCT_REPO="$TARGET_ROOT/auto-games"
  elif [ -d "$TARGET_ROOT/.git" ]; then
    PRODUCT_REPO="$TARGET_ROOT"
  else
    PRODUCT_REPO="$DASHBOARD_ROOT"
  fi
fi

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

cleanup() {
  local code="${1:-0}"
  trap - EXIT INT TERM
  for pid in "${SYNC_PID:-}" "${AGG_PID:-}" "${HTTP_PID:-}"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  exit "$code"
}

trap 'cleanup 0' EXIT
trap 'cleanup 130' INT TERM

require npm
require npx
require python3

mkdir -p "$RUNTIME_DIR"

if [ -z "$R2_UPLOAD_URL" ] && [ -n "${R2_S3_ENDPOINT:-}" ] && [ -n "${R2_BUCKET:-}" ] && [ -n "${R2_ACCESS_KEY_ID:-}" ] && [ -n "${R2_SECRET_ACCESS_KEY:-}" ]; then
  if [ ! -f "$PRESIGN_TOOL" ]; then
    echo "Missing presign helper: $PRESIGN_TOOL" >&2
    exit 1
  fi
  R2_UPLOAD_URL="$(
    python3 "$PRESIGN_TOOL" \
      --endpoint "$R2_S3_ENDPOINT" \
      --bucket "$R2_BUCKET" \
      --key "${R2_OBJECT_KEY:-state/live-state.json}" \
      --access-key-id "$R2_ACCESS_KEY_ID" \
      --secret-access-key "$R2_SECRET_ACCESS_KEY" \
      --region "${R2_REGION:-auto}" \
      --expires "${R2_PRESIGN_TTL_SECS:-604800}"
  )"
fi

if [ ! -d "$SITE_DIR/node_modules" ]; then
  echo "[dashboard] installing site dependencies..."
  (cd "$SITE_DIR" && npm install)
fi

echo "[dashboard] building site..."
(cd "$SITE_DIR" && npm run build)

echo "[dashboard] target root: $TARGET_ROOT"
if [ -n "$MILLRACE_WORKSPACE" ]; then
  echo "[dashboard] millrace workspace: $MILLRACE_WORKSPACE"
  echo "[dashboard] product repo: $PRODUCT_REPO"
else
  echo "[dashboard] research log: $RESEARCH_LOG"
  echo "[dashboard] orchestrate log: $ORCHESTRATE_LOG"
fi
echo "[dashboard] dashboard log: $DASHBOARD_LOG"
echo "[dashboard] state json: $STATE_JSON"
echo "[dashboard] tracker timezone: $TRACKER_TZ"
if [ -n "$R2_PUBLIC_URL" ]; then
  echo "[dashboard] public state url: $R2_PUBLIC_URL"
fi

: >"$HTTP_LOG"
: >"$AGG_LOG"
: >"$SYNC_LOG"
rm -f "$DASHBOARD_LOG"

(cd "$SITE_DIR" && npx http-server dist -p "$PORT" -c-1 >>"$HTTP_LOG" 2>&1) &
HTTP_PID=$!

STATE_SYNC_CMD=(
  python3 "$TRACKER_DIR/state_sync.py"
  --repo-path "$PRODUCT_REPO"
  --run-id "$RUN_ID"
  --output-json "$STATE_JSON"
  --tracker-tz "$TRACKER_TZ"
)

if [ -n "$MILLRACE_WORKSPACE" ]; then
  STATE_SYNC_CMD+=(--millrace-workspace "$MILLRACE_WORKSPACE")
else
  python3 "$TRACKER_DIR/log_aggregator.py" \
    --research-log "$RESEARCH_LOG" \
    --orchestrate-log "$ORCHESTRATE_LOG" \
    --repo-root "$TARGET_ROOT" \
    --dashboard-log "$DASHBOARD_LOG" \
    --start-at-end \
    --reset-output-on-start >>"$AGG_LOG" 2>&1 &
  AGG_PID=$!

  STATE_SYNC_CMD+=(--dashboard-log "$DASHBOARD_LOG")
fi

if [ -n "$R2_UPLOAD_URL" ]; then
  STATE_SYNC_CMD+=(--r2-endpoint "$R2_UPLOAD_URL")
else
  STATE_SYNC_CMD+=(--dry-run)
fi

"${STATE_SYNC_CMD[@]}" >>"$SYNC_LOG" 2>&1 &
SYNC_PID=$!

echo
echo "[dashboard] live stack is running"
echo "[dashboard] url: http://127.0.0.1:${PORT}"
echo "[dashboard] logs:"
echo "  - $HTTP_LOG"
if [ -z "$MILLRACE_WORKSPACE" ]; then
  echo "  - $AGG_LOG"
fi
echo "  - $SYNC_LOG"
echo
if [ -n "$MILLRACE_WORKSPACE" ]; then
  echo "[dashboard] state_sync is reading Millrace runtime artifacts directly."
else
  echo "[dashboard] state_sync will publish neutral standby state until fresh dashboard lines arrive."
fi
echo
echo "[dashboard] press Ctrl-C to stop the live stack."

PIDS=("$HTTP_PID" "$SYNC_PID")
if [ -n "${AGG_PID:-}" ]; then
  PIDS+=("$AGG_PID")
fi

wait "${PIDS[@]}"
