"""Dialog API mijozi."""

import httpx

_MAX_TEXT_LENGTH = 2000


class ApiClient:
    def __init__(self, base_url: str, token: str, transport=None) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Internal-Token": token},
            timeout=15,
            transport=transport,
        )

    async def send(self, user_id: int, text: str | None = None, action: str | None = None) -> dict:
        body = {"channel": "telegram", "user_id": str(user_id), "text": None, "action": action}
        if text is not None:
            body["text"] = text[:_MAX_TEXT_LENGTH]
        response = await self._client.post("/api/chat/message", json=body)
        response.raise_for_status()
        return response.json()

    async def pending(self) -> list[dict]:
        response = await self._client.get("/api/internal/pending")
        response.raise_for_status()
        return response.json()

    async def ack(self, message_id: int) -> None:
        response = await self._client.post(f"/api/internal/messages/{message_id}/delivered")
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()
