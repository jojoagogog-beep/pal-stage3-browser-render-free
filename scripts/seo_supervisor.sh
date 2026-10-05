#!/bin/zsh
set -u
BASE="$HOME/pal-shopify-seo-bulk-fixer"
RUNTIME="$BASE/runtime"
ENVFILE="$BASE/.env.production"
PORT="${PORT:-3001}"
TUNNEL_NAME="pal-seo-origin"
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p "$RUNTIME"
log(){ printf "%s %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$RUNTIME/supervisor.log"; }
[[ -f "$ENVFILE" ]] || { log "env_missing"; exit 1; }
set -a; source "$ENVFILE"; set +a
cd "$BASE" || exit 1
/opt/homebrew/bin/npx prisma db push >>"$RUNTIME/supervisor.log" 2>&1 || exit 1
while true; do
  log "starting_app"
  PORT="$PORT" /opt/homebrew/bin/npm run start >>"$RUNTIME/app.log" 2>&1 &
  APP_PID=$!
  READY=0
  for _ in {1..30}; do
    if /usr/bin/curl -fsS "http://127.0.0.1:$PORT/privacy" >/dev/null 2>&1; then READY=1; break; fi
    sleep 1
  done
  if [[ "$READY" -ne 1 ]]; then log "app_not_ready"; kill "$APP_PID" 2>/dev/null || true; sleep 5; continue; fi
  : > "$RUNTIME/tunnel.log"
  log "starting_tunnel=$TUNNEL_NAME"
  (
    cd "$BASE/gateway" || exit 1
    /opt/homebrew/bin/npx wrangler tunnel run "$TUNNEL_NAME" --log-level info
  ) >>"$RUNTIME/tunnel.log" 2>&1 &
  TUN_PID=$!
  TUN_READY=0
  for _ in {1..30}; do
    if /usr/bin/grep -q "Registered tunnel connection" "$RUNTIME/tunnel.log" 2>/dev/null; then TUN_READY=1; break; fi
    sleep 1
  done
  [[ "$TUN_READY" -eq 1 ]] && log "tunnel_healthy" || log "tunnel_not_ready"
  while kill -0 "$APP_PID" 2>/dev/null && kill -0 "$TUN_PID" 2>/dev/null; do sleep 10; done
  log "child_stopped_restarting"
  kill "$APP_PID" "$TUN_PID" 2>/dev/null || true
  wait "$APP_PID" 2>/dev/null || true
  wait "$TUN_PID" 2>/dev/null || true
  sleep 5
done
