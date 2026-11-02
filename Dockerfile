FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

ENV CHAT_HOST="0.0.0.0"
ENV CHAT_PORT=7070
ENV CHAT_SCALE_MODE="autonome"
ENV CHAT_SECRET="melodi_chat_secret_789"
ENV WEBSOCKET_BROADCAST_URL="http://melodi_websocket:3002/internal/broadcast"
ENV WEBSOCKET_SECRET="melodi_ws_secret_456"

EXPOSE 7070

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:7070/health || exit 1

ENTRYPOINT ["./start.sh"]
