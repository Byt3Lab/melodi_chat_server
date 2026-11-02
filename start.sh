#!/usr/bin/env bash
# Démarrage de Melodi Chat Server

PORT="${1:-${CHAT_PORT:-7070}}"
SCALE_MODE="${2:-${CHAT_SCALE_MODE:-autonome}}"
SECRET="${3:-${CHAT_SECRET:-melodi_chat_secret_789}}"
HOST="${4:-${CHAT_HOST:-0.0.0.0}}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "Démarrage de Melodi Chat Server sur http://$HOST:$PORT (Mode: $SCALE_MODE)..."
exec python3 main.py --host "$HOST" --port "$PORT" --scale-mode "$SCALE_MODE" --secret "$SECRET" "$@"
