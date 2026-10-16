#!/usr/bin/env bash
set -euo pipefail

# Restart the V-Base preview stack (frontend live proxy + local backend).
# Intended for `apps/web`, but safe to run from the repository root too.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$REPO_ROOT"

echo "==> Killing any process listening on :5173 or :8000 in this worktree..."

for port in 5173 8000; do
  pids=$(netstat -ano 2>/dev/null | awk -v p=":${port}" '$0 ~ p && $0 ~ /LISTEN/ { print $NF }' | sort -u || true)
  if [ -n "$pids" ]; then
    for pid in $pids; do
      taskkill //PID "$pid" //F //T >/dev/null 2>&1 || true
      echo "    killed PID $pid on port $port"
    done
  fi
done

# Give the OS a moment to release the sockets.
sleep 1

echo "==> Starting backend API on :8000 (no --reload, single worker)..."
cd "$REPO_ROOT/backend"
nohup python -m nexus.commands.run --port 8000 --host 127.0.0.1 --log-level info > "$REPO_ROOT/backend/run.log" 2>&1 &
echo "    backend PID $!"

echo "==> Waiting for :8000 to answer /health..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health | grep -q 200; then
    echo "    backend is up"
    break
  fi
  sleep 1
done

status=$(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo '{"status":"unknown"}')
echo "    /health => $status"
ready=$(curl -s http://127.0.0.1:8000/health/ready 2>/dev/null || echo '{"status":"unknown"}')
echo "    /health/ready => $ready"

echo "==> Starting frontend dev proxy on :5173 (from apps/web)..."
cd "$REPO_ROOT/apps/web"
nohup npx --yes vite --host 0.0.0.0 --port 5173 > "$REPO_ROOT/apps/web/vite.log" 2>&1 &
echo "    vite PID $!"

echo "==> Waiting for :5173 to serve /..."
for i in $(seq 1 40); do
  if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173/ | grep -qE "200|301|302"; then
    echo "    frontend is up"
    break
  fi
  sleep 1
done

echo "==> done. Logs:"
echo "    backend: $REPO_ROOT/backend/run.log"
echo "    frontend: $REPO_ROOT/apps/web/vite.log"
