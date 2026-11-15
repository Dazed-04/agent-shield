"""Thread-safe Server-Sent-Events broadcaster with per-subscriber visibility filtering."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

Event = tuple[str, Any]


@dataclass(eq=False)
class Subscriber:
    queue: "asyncio.Queue[Event]"
    loop: asyncio.AbstractEventLoop
    user: str | None
    is_admin: bool


class SSEBroadcaster:
    """Pushes gateway events to connected clients.

    ``publish_sync`` may be called from FastAPI's worker threads (sync routes), so delivery
    is marshalled onto each subscriber's own event loop with ``call_soon_threadsafe``.
    Queues are bounded; a slow client is dropped rather than growing memory without limit.
    """

    def __init__(self, max_queue: int = 200) -> None:
        self.subscribers: set[Subscriber] = set()
        self.max_queue = max_queue

    async def subscribe(self, user: str | None, is_admin: bool) -> Subscriber:
        sub = Subscriber(
            queue=asyncio.Queue(maxsize=self.max_queue),
            loop=asyncio.get_running_loop(),
            user=user,
            is_admin=is_admin,
        )
        self.subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self.subscribers.discard(sub)

    @staticmethod
    def _put(sub: Subscriber, item: Event) -> None:
        try:
            sub.queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning("Dropping slow SSE subscriber")
            sub.is_admin = False
            sub.user = None  # receives nothing further; its connection loop will time out

    def publish_sync(
        self,
        event_type: str,
        data: Any,
        owner: str | None = None,
        admin_only: bool = False,
    ) -> None:
        """Deliver to admins always; to a regular user only for events they own."""
        for sub in list(self.subscribers):
            allowed = sub.is_admin or (
                not admin_only and owner is not None and sub.user == owner
            )
            if not allowed:
                continue
            try:
                sub.loop.call_soon_threadsafe(self._put, sub, (event_type, data))
            except RuntimeError:  # loop closed
                self.subscribers.discard(sub)


broadcaster = SSEBroadcaster()
