"""
WebSocket Publisher for melodi_chat_server.
Broadcasts chat events to the melodi_websocket service.
"""

import logging
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("melodi_chat_server.websocket_publisher")


class WebSocketPublisher:
    def __init__(self, ws_url: str, secret: str):
        self.ws_url = ws_url.rstrip("/")
        self.secret = secret

    async def broadcast(
        self,
        event: str,
        data: Dict[str, Any],
        user_ids: Optional[List[int]] = None,
        channels: Optional[List[str]] = None,
    ) -> bool:
        """
        Sends an internal broadcast payload to melodi_websocket.
        """
        if self.ws_url.endswith("/internal/broadcast") or self.ws_url.endswith("/internal/emit"):
            target_url = self.ws_url
        else:
            target_url = f"{self.ws_url}/internal/broadcast"

        payload = {
            "event": event,
            "data": data,
        }
        if user_ids is not None:
            payload["user_ids"] = user_ids
        if channels is not None:
            payload["channels"] = channels

        headers = {
            "X-Internal-Secret": self.secret,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(target_url, json=payload, headers=headers)
                if res.status_code == 200:
                    logger.debug(f"Broadcast event '{event}' sent successfully: {res.json()}")
                    return True
                else:
                    logger.warning(
                        f"Failed to broadcast '{event}' to {target_url}: status={res.status_code} body={res.text}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"Error publishing to WebSocket service at {target_url}: {e}")
            return False
