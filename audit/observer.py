"""Audit Observer (GoF Observer).

``AuditObserver`` attaches to a ``MatchState`` (the Subject) and, on every
notified mutation, appends one immutable event to the :class:`EventStore`. It
back-fills the assigned ``seq`` onto the live event dict so the domain reducer
and any downstream consumers see the same sequence number that was persisted.
"""
from __future__ import annotations

from audit.event_store import EventStore


class AuditObserver:
    def __init__(self, store: EventStore) -> None:
        self._store = store
        self.count = 0

    def on_event(self, subject, event: dict) -> None:
        seq = self._store.append(
            subject.match_id,
            event["type"],
            event.get("actor"),
            event.get("payload", {}),
        )
        event["seq"] = seq  # back-fill so the reducer records last_seq
        self.count += 1
