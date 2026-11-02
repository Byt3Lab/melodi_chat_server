# MELODI Chat Server (`melodi_chat_server`)

Microservice dédié pour la messagerie instantanée de MELODI ERP, opérant sur le **port 7070**.
Il isole entièrement la persistance et la gestion des conversations (canaux, discussions directes, groupes, messages) afin de soulager la base de données principale de l'ERP.

## Architecture

- **Port** : `7070`
- **Technologie** : Quart (Python asynchrone) + Hypercorn (ASGI) + SQLAlchemy 2.0 (asyncio)
- **Base de données** : SQLite asynchrone (`chat.db`) ou PostgreSQL
- **Diffusion temps réel** : `melodi_websocket` via l'API interne (`/internal/broadcast`)
- **Scalabilité horizontale** :
  - `CHAT_SCALE_MODE=autonome` : Mode local autonome
  - `CHAT_SCALE_MODE=scalable` : Mode distribué avec Redis (ping obligatoire au démarrage)

## Démarrage rapide

### En local (script bash)
```bash
./start.sh 7070 autonome melodi_chat_secret_789
```

### Avec Docker
```bash
docker build -t melodi_chat_server .
docker run -p 7070:7070 \
  -e CHAT_PORT=7070 \
  -e CHAT_SCALE_MODE=autonome \
  -e CHAT_SECRET=melodi_chat_secret_789 \
  melodi_chat_server
```

## Endpoints principaux

- `GET /health` : Vérification d'état, mode de scaling, connectivité DB et Redis
- `GET /conversations` : Liste des conversations
- `POST /conversations/direct` : Créer ou récupérer une discussion directe
- `POST /conversations/group` : Créer un groupe
- `DELETE /conversations/<id>` : Supprimer une conversation
- `GET /messages?conv_id=<id>` : Récupérer les messages
- `POST /messages` : Envoyer un message (déclenche diffusion WebSocket)
- `DELETE /messages/<id>` : Supprimer un message
- `POST /typing` : Diffuser un indicateur de saisie en temps réel
