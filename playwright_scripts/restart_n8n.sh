#!/bin/zsh
# Kill n8n
ROOT="${JOBHUNT_ROOT:-$HOME/JobHunt}"
PID=$(cat "$ROOT/.n8n.pid" 2>/dev/null)
if [ ! -z "$PID" ]; then
  kill -9 $PID 2>/dev/null || true
fi
pkill -9 -f "n8n start" || true

# Wait 2 seconds
sleep 2

# Start n8n with Execute Command node enabled
N8N_BASIC_AUTH_ACTIVE=true \
N8N_BASIC_AUTH_USER="${N8N_BASIC_AUTH_USER:-reviewer}" \
N8N_BASIC_AUTH_PASSWORD="${N8N_BASIC_AUTH_PASSWORD:-change-me-before-use}" \
N8N_HOST="${N8N_HOST:-n8n.example.com}" \
N8N_PORT=5678 \
N8N_PROTOCOL=https \
WEBHOOK_URL="${WEBHOOK_URL:-https://n8n.example.com/}" \
N8N_EDITOR_BASE_URL="${N8N_EDITOR_BASE_URL:-https://n8n.example.com/}" \
N8N_RUNNERS_ENABLED=true \
N8N_DIAGNOSTICS_ENABLED=false \
N8N_NODES_EXCLUDE="[]" \
NODES_EXCLUDE="[]" \
nohup /opt/homebrew/bin/n8n start > "$ROOT/logs/n8n.log" 2>&1 &
echo $! > "$ROOT/.n8n.pid"; disown

echo "[+] n8n restarted with Execute Command node enabled!"
