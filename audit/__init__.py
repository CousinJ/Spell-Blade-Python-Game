"""Audit / persistence layer.

Append-only SQLite event store (event sourcing) with point-in-time ``replay``
(``event_store``), and the Observer that records every notified mutation as an
immutable event (``observer``).
"""
