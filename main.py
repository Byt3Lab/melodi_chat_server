"""
MELODI Dedicated Chat Server (melodi_chat_server)
Runs as an independent high-performance microservice on port 7070.
Handles all chat conversations, direct messages, groups, channels, and message persistence.
Delegates real-time delivery and scaling to melodi_websocket and optional Redis cluster.
"""

import sys
import os
import logging
from typing import Optional
from quart import Quart, request, jsonify

# Prepend local venv site-packages if running standalone
venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "lib")
if os.path.isdir(venv_dir):
    for entry in os.listdir(venv_dir):
        sp = os.path.join(venv_dir, entry, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

from config import load_config, mask_db_url, get_db_type, save_server_config
from database import DatabaseManager
from services.websocket_publisher import WebSocketPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [melodi_chat_server] %(message)s"
)
logger = logging.getLogger("melodi_chat_server")

config = load_config()
app = Quart(__name__)

db_manager = DatabaseManager(config.db_url)
ws_publisher = WebSocketPublisher(config.websocket_broadcast_url, config.websocket_secret)

redis_client = None


def check_auth() -> bool:
    """Verifies internal secret from headers."""
    secret = (
        request.headers.get("X-Melodi-Secret")
        or request.headers.get("X-Internal-Secret")
    )
    if secret and secret == config.secret:
        return True

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        if token == config.secret:
            return True

    return False


async def check_redis_alive(host: str, port: int, password: Optional[str] = None) -> bool:
    try:
        import redis.asyncio as aioredis
        client = aioredis.Redis(host=host, port=port, password=password or None, socket_timeout=2.0)
        res = await client.ping()
        await client.aclose()
        return bool(res)
    except Exception as e:
        logger.warning(f"[Redis Check] Ping failed to {host}:{port}: {e}")
        return False


@app.before_serving
async def startup():
    logger.info(f"Démarrage de Melodi Chat Server sur le port {config.port} (mode: {config.scale_mode})")
    
    # Check scalable mode requirements
    if config.scale_mode == "scalable":
        logger.info(f"Vérification de la connectivité Redis sur {config.redis_host}:{config.redis_port}...")
        is_alive = await check_redis_alive(config.redis_host, config.redis_port, config.redis_password)
        if not is_alive:
            err_msg = (
                f"ÉCHEC DE DÉMARRAGE: Mode 'scalable' activé mais Redis ({config.redis_host}:{config.redis_port}) "
                "est indisponible ou injoignable. Le serveur de chat refuse de démarrer en mode dégradé."
            )
            logger.critical(err_msg)
            raise RuntimeError(err_msg)
        logger.info("Connexion Redis validée avec succès pour le mode scalable.")

    # Initialize Database tables and default channels
    try:
        await db_manager.init_db()
        logger.info(f"Base de données chat initialisée ({config.db_url}).")
    except Exception as e:
        logger.critical(f"Erreur fatale lors de l'initialisation de la base de données: {e}")
        raise


@app.route("/health", methods=["GET"])
async def health():
    db_ok, db_msg = await db_manager.check_health()
    redis_status = "disabled"
    if config.scale_mode == "scalable":
        r_ok = await check_redis_alive(config.redis_host, config.redis_port, config.redis_password)
        redis_status = "connected" if r_ok else "disconnected"

    stats = await db_manager.get_stats()

    return jsonify({
        "status": "ok" if db_ok else "error",
        "service": "melodi_chat_server",
        "port": config.port,
        "scale_mode": config.scale_mode,
        "db_status": "connected" if db_ok else "error",
        "db_type": get_db_type(db_manager.db_url),
        "db_url_masked": mask_db_url(db_manager.db_url),
        "db_message": db_msg,
        "redis_status": redis_status,
        "stats": stats
    }), 200 if db_ok else 503


@app.route("/test-db", methods=["POST"])
async def test_db():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = await request.get_json() or {}
    candidate_url = data.get("db_url", "").strip()
    if not candidate_url:
        return jsonify({"status": "error", "message": "Le paramètre db_url est requis"}), 400

    ok, msg = await DatabaseManager.test_connection(candidate_url)
    if ok:
        return jsonify({
            "status": "success",
            "message": f"Connexion réussie à la base ({get_db_type(candidate_url)})",
            "db_type": get_db_type(candidate_url),
            "db_url_masked": mask_db_url(candidate_url)
        })
    return jsonify({
        "status": "error",
        "message": f"Échec de connexion : {msg}"
    }), 400


@app.route("/config", methods=["POST"])
async def update_config():
    global config
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = await request.get_json() or {}

    new_db_url = data.get("db_url")
    if new_db_url and new_db_url.strip() and new_db_url.strip() != db_manager.db_url:
        target_url = new_db_url.strip()
        ok, msg = await DatabaseManager.test_connection(target_url)
        if not ok:
            return jsonify({
                "status": "error",
                "message": f"Connexion échouée à la nouvelle base : {msg}"
            }), 400

        try:
            await db_manager.reconnect(target_url)
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"Erreur lors de l'initialisation de la nouvelle base : {str(e)}"
            }), 500

    # Persist in server config file
    save_server_config(data)
    # Reload local config
    config = load_config()

    return jsonify({
        "status": "success",
        "message": "Configuration du serveur de chat mise à jour avec succès",
        "db_type": get_db_type(db_manager.db_url),
        "db_url_masked": mask_db_url(db_manager.db_url),
        "scale_mode": config.scale_mode
    })


@app.route("/stats", methods=["GET"])
async def stats():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    stats_data = await db_manager.get_stats()
    return jsonify({"status": "success", "data": stats_data}), 200


@app.route("/conversations", methods=["GET"])
async def get_conversations():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    user_id = request.args.get("user_id")
    convs = await db_manager.get_conversations(current_user_id=user_id)
    return jsonify({
        "status": "success",
        "conversations": [c.to_dict() for c in convs]
    }), 200


@app.route("/conversations/<int:conv_id>", methods=["GET"])
async def get_conversation(conv_id: int):
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    conv = await db_manager.get_conversation(conv_id)
    if not conv:
        return jsonify({"status": "error", "message": "Conversation introuvable"}), 404

    return jsonify({
        "status": "success",
        "conversation": conv.to_dict()
    }), 200


@app.route("/conversations/direct", methods=["POST"])
async def create_direct_conversation():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    body = await request.get_json() or {}
    user1_id = str(body.get("current_user_id", ""))
    user1_name = str(body.get("current_user_name", "Utilisateur"))
    user2_id = str(body.get("target_user_id", ""))
    user2_name = str(body.get("target_user_name", "Contact"))

    if not user1_id or not user2_id:
        return jsonify({"status": "error", "message": "current_user_id et target_user_id requis"}), 400

    conv = await db_manager.get_or_create_direct_conversation(
        user1_id=user1_id,
        user1_name=user1_name,
        user2_id=user2_id,
        user2_name=user2_name
    )
    return jsonify({
        "status": "success",
        "conversation": conv.to_dict()
    }), 200


@app.route("/conversations/group", methods=["POST"])
async def create_group_conversation():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    body = await request.get_json() or {}
    title = body.get("title", "").strip()
    if not title:
        return jsonify({"status": "error", "message": "Le titre du groupe est requis"}), 400

    description = body.get("description", "")
    created_by_id = body.get("created_by_id")
    created_by_name = body.get("created_by_name", "Admin")
    member_ids = body.get("member_ids", [])

    conv = await db_manager.create_group_conversation(
        title=title,
        description=description,
        created_by_id=str(created_by_id) if created_by_id else None,
        created_by_name=created_by_name,
        member_ids=member_ids
    )

    # Broadcast event to WebSocket so clients update conversation list immediately
    await ws_publisher.broadcast(
        event="chat_conversation_created",
        data={"conversation": conv.to_dict()}
    )

    return jsonify({
        "status": "success",
        "conversation": conv.to_dict()
    }), 201


@app.route("/conversations/<int:conv_id>", methods=["DELETE"])
async def delete_conversation(conv_id: int):
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    ok = await db_manager.delete_conversation(conv_id)
    if not ok:
        return jsonify({"status": "error", "message": "Conversation introuvable"}), 404

    # Broadcast deletion event
    await ws_publisher.broadcast(
        event="chat_conversation_deleted",
        data={"conversation_id": conv_id}
    )

    return jsonify({"status": "success", "message": "Conversation supprimée"}), 200


@app.route("/messages", methods=["GET"])
async def get_messages():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    conv_id = request.args.get("conv_id", type=int)
    if not conv_id:
        return jsonify({"status": "error", "message": "conv_id requis"}), 400

    limit = request.args.get("limit", default=50, type=int)
    messages = await db_manager.get_messages(conversation_id=conv_id, limit=limit)

    return jsonify({
        "status": "success",
        "messages": [m.to_dict() for m in messages]
    }), 200


@app.route("/messages", methods=["POST"])
async def create_message():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    body = await request.get_json() or {}
    conv_id = body.get("conversation_id")
    sender_id = body.get("sender_id")
    sender_name = body.get("sender_name", "Utilisateur")
    sender_avatar = body.get("sender_avatar")
    text = (body.get("message") or "").strip()

    if not conv_id or not text:
        return jsonify({"status": "error", "message": "conversation_id et message requis"}), 400

    msg = await db_manager.create_message(
        conversation_id=int(conv_id),
        sender_id=str(sender_id) if sender_id else None,
        sender_name=sender_name,
        message=text,
        sender_avatar=sender_avatar
    )

    msg_dict = msg.to_dict()

    # Determine recipients: if direct conversation, parse target user IDs
    user_ids = None
    conv = await db_manager.get_conversation(int(conv_id))
    if conv and conv.code.startswith("direct_"):
        parts = conv.code.replace("direct_", "").split("_")
        user_ids = []
        for p in parts:
            if p.isdigit():
                user_ids.append(int(p))
        if not user_ids:
            user_ids = None

    # Broadcast to melodi_websocket
    await ws_publisher.broadcast(
        event="chat_message",
        data=msg_dict,
        user_ids=user_ids
    )

    return jsonify({
        "status": "success",
        "message": msg_dict
    }), 201


@app.route("/messages/<int:msg_id>", methods=["DELETE"])
async def delete_message(msg_id: int):
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    ok, conv_id = await db_manager.delete_message(msg_id)
    if not ok:
        return jsonify({"status": "error", "message": "Message introuvable"}), 404

    # Determine recipients if direct
    user_ids = None
    if conv_id:
        conv = await db_manager.get_conversation(conv_id)
        if conv and conv.code.startswith("direct_"):
            parts = conv.code.replace("direct_", "").split("_")
            user_ids = [int(p) for p in parts if p.isdigit()] or None

    await ws_publisher.broadcast(
        event="chat_message_deleted",
        data={
            "message_id": msg_id,
            "conversation_id": conv_id
        },
        user_ids=user_ids
    )

    return jsonify({"status": "success", "message": "Message supprimé"}), 200


@app.route("/typing", methods=["POST"])
async def broadcast_typing():
    if not check_auth():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    body = await request.get_json() or {}
    conv_id = body.get("conversation_id")
    user_id = body.get("user_id")
    user_name = body.get("user_name", "Utilisateur")

    if not conv_id:
        return jsonify({"status": "error", "message": "conversation_id requis"}), 400

    user_ids = None
    conv = await db_manager.get_conversation(int(conv_id))
    if conv and conv.code.startswith("direct_"):
        parts = conv.code.replace("direct_", "").split("_")
        user_ids = [int(p) for p in parts if p.isdigit()] or None

    await ws_publisher.broadcast(
        event="chat_typing",
        data={
            "conversation_id": int(conv_id),
            "user_id": user_id,
            "user_name": user_name,
            "sender_name": user_name
        },
        user_ids=user_ids
    )

    return jsonify({"status": "success"}), 200


if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config as HypercornConfig

    h_config = HypercornConfig()
    h_config.bind = [f"{config.host}:{config.port}"]
    h_config.use_reloader = False

    import asyncio
    asyncio.run(hypercorn.asyncio.serve(app, h_config))
