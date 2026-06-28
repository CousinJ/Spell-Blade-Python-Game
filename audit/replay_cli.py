"""CLI: reconstruct point-in-time match state from the audit log.

    python -m audit.replay_cli <db_path> --list
    python -m audit.replay_cli <db_path> <match_id>
    python -m audit.replay_cli <db_path> <match_id> --upto <seq>
    python -m audit.replay_cli <db_path> <match_id> --events     # raw event log

This is the live-demo proof that every mutation is reconstructable.
"""
from __future__ import annotations

import argparse
import json
import sys

from audit.event_store import EventStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay match state from the audit log.")
    parser.add_argument("db", help="path to the SQLite audit db")
    parser.add_argument("match_id", nargs="?", help="match id to reconstruct")
    parser.add_argument("--upto", type=int, default=None, help="reconstruct up to this seq")
    parser.add_argument("--list", action="store_true", help="list match ids and exit")
    parser.add_argument("--events", action="store_true", help="print the raw event log")
    args = parser.parse_args(argv)

    store = EventStore(args.db)
    try:
        if args.list or not args.match_id:
            matches = store.matches()
            print(json.dumps({"matches": matches}, indent=2))
            return 0

        if args.events:
            events = store.events_for(args.match_id, args.upto)
            print(json.dumps(events, indent=2))
            return 0

        state = store.replay(args.match_id, args.upto)
        print(json.dumps(state.snapshot(), indent=2))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
