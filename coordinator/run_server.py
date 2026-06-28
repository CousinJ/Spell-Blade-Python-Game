"""Run the Match Coordinator web service (single worker).

    python -m coordinator.run_server          # dev, $PORT or 8000
    uvicorn coordinator.app:app --port 8000   # equivalent

A single uvicorn worker is required: the :class:`PubSubHub` registry lives in
process memory and is not shared across workers.
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "coordinator.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
