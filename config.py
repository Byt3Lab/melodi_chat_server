import os
import json
import argparse
from typing import NamedTuple, Dict, Any
from urllib.parse import urlparse, urlunparse

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_config.json")


class ChatConfig(NamedTuple):
    host: str
    port: int
    secret: str
    scale_mode: str
    db_url: str
    redis_host: str
    redis_port: int
    redis_password: str
    websocket_broadcast_url: str
    websocket_secret: str


def mask_db_url(url: str) -> str:
    """Masque le mot de passe dans l'URL de base de données pour la télémétrie."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        pass
    return url


def get_db_type(url: str) -> str:
    """Retourne le type de moteur de base de données (SQLite, PostgreSQL, etc.)."""
    if not url:
        return "Non configuré"
    url_lower = url.lower()
    if "sqlite" in url_lower:
        return "SQLite"
    if "postgres" in url_lower:
        return "PostgreSQL"
    if "mysql" in url_lower or "mariadb" in url_lower:
        return "MySQL"
    return "SQL (Autre)"


def load_file_config() -> Dict[str, Any]:
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_server_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = load_file_config()
    current.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        print(f"[Config] Erreur sauvegarde {CONFIG_FILE}: {e}")
    return current


def load_config() -> ChatConfig:
    parser = argparse.ArgumentParser(description="MELODI Dedicated Chat Server")
    parser.add_argument("--host", default=None, help="Binding host")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default 7070)")
    parser.add_argument("--secret", default=None, help="Shared internal secret key")
    parser.add_argument("--scale-mode", default=None, choices=["autonome", "scalable"], help="Scale mode: autonome or scalable")
    parser.add_argument("--db-url", default=None, help="SQLAlchemy database URL")
    parser.add_argument("--redis-host", default=None, help="Redis host for scalable mode")
    parser.add_argument("--redis-port", type=int, default=None, help="Redis port for scalable mode")
    parser.add_argument("--redis-password", default=None, help="Redis password")
    parser.add_argument("--ws-url", default=None, help="WebSocket broadcast endpoint")
    parser.add_argument("--ws-secret", default=None, help="WebSocket shared secret")

    args, _ = parser.parse_known_args()
    file_cfg = load_file_config()

    host = args.host or os.environ.get("CHAT_HOST") or file_cfg.get("host", "0.0.0.0")
    port = int(args.port or os.environ.get("CHAT_PORT") or file_cfg.get("port", 7070))
    secret = args.secret or os.environ.get("CHAT_SECRET") or file_cfg.get("secret", "melodi_chat_secret_789")
    scale_mode = (args.scale_mode or os.environ.get("CHAT_SCALE_MODE") or file_cfg.get("scale_mode", "autonome")).strip().lower()
    db_url = args.db_url or os.environ.get("CHAT_DB_URL") or file_cfg.get("db_url", "sqlite+aiosqlite:///chat.db")
    redis_host = args.redis_host or os.environ.get("CHAT_REDIS_HOST") or file_cfg.get("redis_host", "localhost")
    redis_port = int(args.redis_port or os.environ.get("CHAT_REDIS_PORT") or file_cfg.get("redis_port", 6379))
    redis_password = args.redis_password or os.environ.get("CHAT_REDIS_PASSWORD") or file_cfg.get("redis_password", "")
    ws_url = args.ws_url or os.environ.get("WEBSOCKET_BROADCAST_URL") or file_cfg.get("ws_url", "http://127.0.0.1:3002/internal/broadcast")
    ws_secret = args.ws_secret or os.environ.get("WEBSOCKET_SECRET") or file_cfg.get("ws_secret", "melodi_ws_secret_456")

    return ChatConfig(
        host=host,
        port=port,
        secret=secret,
        scale_mode=scale_mode,
        db_url=db_url,
        redis_host=redis_host,
        redis_port=redis_port,
        redis_password=redis_password,
        websocket_broadcast_url=ws_url,
        websocket_secret=ws_secret,
    )
