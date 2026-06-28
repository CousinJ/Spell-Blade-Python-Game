"""Message Router (EIP): content-based dispatch by message ``type``.

The coordinator registers one async handler per message type; :meth:`route`
inspects each inbound envelope and forwards it to the matching handler.

Reference: https://www.enterpriseintegrationpatterns.com/MessageRouter.html
"""
from __future__ import annotations

from typing import Awaitable, Callable

from messaging.schema import Envelope

Handler = Callable[[Envelope, str], Awaitable[None]]


class NoRouteError(KeyError):
    """No handler registered for an envelope's type."""


class MatchRouter:
    def __init__(self) -> None:
        self._routes: dict[str, Handler] = {}

    def register(self, msg_type: str, handler: Handler) -> None:
        self._routes[msg_type] = handler

    def has_route(self, msg_type: str) -> bool:
        return msg_type in self._routes

    async def route(self, env: Envelope, channel: str) -> None:
        handler = self._routes.get(env.type)
        if handler is None:
            raise NoRouteError(env.type)
        await handler(env, channel)
