"""Publish-Subscribe Channel (EIP) — server-side hub.

``PubSubHub`` is the transport-agnostic core of the messaging layer. It maps
channel keys to sets of subscribers and fans every published payload out to that
channel's current subscribers. It also *retains* the last payload per channel and
replays it to a new subscriber (a lightweight "retained message", so a late
joiner immediately receives current state).

Subscribers only need an async ``send(text)`` coroutine and a stable ``id``,
which keeps the hub fully testable without a real socket (see tests).

Reference: https://www.enterpriseintegrationpatterns.com/PublishSubscribeChannel.html
"""
from __future__ import annotations

import asyncio
from typing import Optional, Protocol


class Subscriber(Protocol):
    id: str

    async def send(self, text: str) -> None: ...


class PubSubHub:
    def __init__(self, retain: bool = True) -> None:
        self._channels: dict[str, set[Subscriber]] = {}
        self._retained: dict[str, str] = {}
        self._retain = retain

    # -- introspection -----------------------------------------------------
    def channels(self) -> list[str]:
        return list(self._channels)

    def subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, ()))

    # -- subscription ------------------------------------------------------
    async def subscribe(
        self, channel: str, sub: Subscriber, *, replay_retained: bool = True
    ) -> None:
        self._channels.setdefault(channel, set()).add(sub)
        if replay_retained and self._retain and channel in self._retained:
            await self._safe_send(sub, self._retained[channel])

    async def unsubscribe(self, channel: str, sub: Subscriber) -> None:
        subs = self._channels.get(channel)
        if subs:
            subs.discard(sub)
            if not subs:
                self._channels.pop(channel, None)

    async def unsubscribe_all(self, sub: Subscriber) -> None:
        for channel in list(self._channels):
            await self.unsubscribe(channel, sub)

    # -- publish -----------------------------------------------------------
    async def publish(
        self, channel: str, text: str, *, retain: Optional[bool] = None
    ) -> int:
        """Fan ``text`` out to every subscriber of ``channel``.

        Returns the number of subscribers the message was delivered to.
        Subscribers whose send raises (e.g. a dropped socket) are removed.
        """
        if retain if retain is not None else self._retain:
            self._retained[channel] = text

        subs = list(self._channels.get(channel, ()))
        if not subs:
            return 0

        results = await asyncio.gather(
            *(self._safe_send(s, text) for s in subs), return_exceptions=True
        )
        delivered = 0
        for sub, ok in zip(subs, results):
            if ok is True:
                delivered += 1
            else:
                await self.unsubscribe(channel, sub)
        return delivered

    # -- internal ----------------------------------------------------------
    async def _safe_send(self, sub: Subscriber, text: str) -> bool:
        try:
            await sub.send(text)
            return True
        except Exception:
            return False
