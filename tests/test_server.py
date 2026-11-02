import pytest
import pytest_asyncio
import os
import sys

# Ensure server package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app, db_manager, check_redis_alive


@pytest_asyncio.fixture(autouse=True)
async def init_test_db():
    await db_manager.init_db()


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"X-Melodi-Secret": "melodi_chat_secret_789"}


@pytest.mark.asyncio
async def test_health_endpoint(client):
    res = await client.get("/health")
    assert res.status_code == 200
    data = await res.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "melodi_chat_server"
    assert data["port"] == 7070
    assert "stats" in data


@pytest.mark.asyncio
async def test_auth_unauthorized(client):
    res = await client.get("/conversations")
    assert res.status_code == 401
    res = await client.get("/messages?conv_id=1")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_conversations(client, auth_headers):
    res = await client.get("/conversations", headers=auth_headers)
    assert res.status_code == 200
    data = await res.get_json()
    assert data["status"] == "success"
    convs = data["conversations"]
    assert len(convs) >= 3
    codes = [c["code"] for c in convs]
    assert "general" in codes
    assert "ventes" in codes
    assert "support" in codes


@pytest.mark.asyncio
async def test_create_direct_conversation(client, auth_headers):
    payload = {
        "current_user_id": 1,
        "current_user_name": "Alice",
        "target_user_id": 2,
        "target_user_name": "Bob"
    }
    res = await client.post("/conversations/direct", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = await res.get_json()
    assert data["status"] == "success"
    conv = data["conversation"]
    assert conv["code"] == "direct_1_2"
    assert conv["type"] == "direct"


@pytest.mark.asyncio
async def test_create_group_conversation(client, auth_headers):
    payload = {
        "title": "Groupe Équipe Dev",
        "description": "Canal de développement",
        "created_by_id": 1,
        "created_by_name": "Alice",
        "member_ids": [1, 2, 3]
    }
    res = await client.post("/conversations/group", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = await res.get_json()
    assert data["status"] == "success"
    conv = data["conversation"]
    assert conv["title"] == "Groupe Équipe Dev"
    assert conv["code"].startswith("group_")


@pytest.mark.asyncio
async def test_messages_crud(client, auth_headers):
    # 1. Get first conversation
    res = await client.get("/conversations", headers=auth_headers)
    convs = (await res.get_json())["conversations"]
    conv_id = convs[0]["id"]

    # 2. Post message
    msg_payload = {
        "conversation_id": conv_id,
        "sender_id": 1,
        "sender_name": "Alice",
        "message": "Bonjour tout le monde !"
    }
    res = await client.post("/messages", json=msg_payload, headers=auth_headers)
    assert res.status_code == 201
    msg_data = await res.get_json()
    assert msg_data["status"] == "success"
    msg = msg_data["message"]
    assert msg["message"] == "Bonjour tout le monde !"
    msg_id = msg["id"]

    # 3. Retrieve messages
    res = await client.get(f"/messages?conv_id={conv_id}", headers=auth_headers)
    assert res.status_code == 200
    msgs = (await res.get_json())["messages"]
    assert any(m["id"] == msg_id for m in msgs)

    # 4. Delete message
    res = await client.delete(f"/messages/{msg_id}", headers=auth_headers)
    assert res.status_code == 200
    del_data = await res.get_json()
    assert del_data["status"] == "success"

    # Verify deleted
    res = await client.get(f"/messages?conv_id={conv_id}", headers=auth_headers)
    msgs = (await res.get_json())["messages"]
    assert not any(m["id"] == msg_id for m in msgs)


@pytest.mark.asyncio
async def test_delete_conversation(client, auth_headers):
    # Create group to delete
    res = await client.post("/conversations/group", json={
        "title": "Groupe Temporaire",
        "created_by_id": 1
    }, headers=auth_headers)
    conv_id = (await res.get_json())["conversation"]["id"]

    # Delete conversation
    res = await client.delete(f"/conversations/{conv_id}", headers=auth_headers)
    assert res.status_code == 200

    # Verify not found
    res = await client.get(f"/conversations/{conv_id}", headers=auth_headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_typing_endpoint(client, auth_headers):
    res = await client.post("/typing", json={
        "conversation_id": 1,
        "user_id": 1,
        "user_name": "Alice"
    }, headers=auth_headers)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_redis_check_failure():
    # Ping an unreachable port
    alive = await check_redis_alive(host="127.0.0.1", port=59999)
    assert alive is False


@pytest.mark.asyncio
async def test_scalable_mode_redis_refusal(monkeypatch):
    import main
    new_cfg = main.config._replace(scale_mode="scalable", redis_host="127.0.0.1", redis_port=59999)
    monkeypatch.setattr(main, "config", new_cfg)

    with pytest.raises(RuntimeError) as exc_info:
        await main.startup()
    assert "ÉCHEC DE DÉMARRAGE: Mode 'scalable' activé mais Redis" in str(exc_info.value)

