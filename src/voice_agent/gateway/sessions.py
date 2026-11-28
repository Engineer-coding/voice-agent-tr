"""Görüşme durumunun saklanması.

Durum her turdan sonra yazılır; bağlantı koparsa istemci aynı `session_id` ile devam eder.
Üretimde Redis, testlerde ve tek süreçli geliştirmede bellek kullanılır.
"""

from typing import Any, Protocol

from voice_agent.dialogue.models import ConversationState

SESSION_TTL_S = 3600


class SessionStore(Protocol):
    async def load(self, session_id: str) -> ConversationState | None: ...

    async def save(self, session_id: str, state: ConversationState) -> None: ...

    async def ping(self) -> bool: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def load(self, session_id: str) -> ConversationState | None:
        raw = self._data.get(session_id)
        return ConversationState.model_validate_json(raw) if raw else None

    async def save(self, session_id: str, state: ConversationState) -> None:
        self._data[session_id] = state.model_dump_json()

    async def ping(self) -> bool:
        return True


class RedisSessionStore:
    def __init__(self, url: str, ttl_s: int = SESSION_TTL_S) -> None:
        from redis.asyncio import Redis

        self._redis: Any = Redis.from_url(url)
        self._ttl_s = ttl_s

    @staticmethod
    def _key(session_id: str) -> str:
        return f"session:{session_id}"

    async def load(self, session_id: str) -> ConversationState | None:
        raw = await self._redis.get(self._key(session_id))
        return ConversationState.model_validate_json(raw) if raw else None

    async def save(self, session_id: str, state: ConversationState) -> None:
        await self._redis.set(self._key(session_id), state.model_dump_json(), ex=self._ttl_s)

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
