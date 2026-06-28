import os

# Pure-data constants shared with the server (no pygame import here).
from coordinator.action_data import MAX_HP, MAX_STAMINA, START_DIR, START_X

WIDTH = 1200
HEIGHT = 1000

# Player render box (matches the original server-spawned players).
PLAYER_W = 80
PLAYER_H = 160
PLAYER_Y = HEIGHT - 200  # 800
PLAYER_COLORS = {"p1": (255, 0, 0), "p2": (0, 0, 255)}

# Networking: clients connect *out* to the coordinator's WebSocket URL.
# Defaults to the deployed Railway coordinator so a fresh clone just works:
#     python client.py
# For local development against your own server, override it, e.g.:
#     SPELLBLADE_WS_URL=ws://localhost:8000/ws python client.py
WS_URL = os.environ.get(
    "SPELLBLADE_WS_URL",
    "wss://spell-blade-python-game-production.up.railway.app/ws",
)

# How often the client publishes its local input/state (Hz).
INPUT_PUBLISH_HZ = 30

__all__ = [
    "WIDTH", "HEIGHT", "PLAYER_W", "PLAYER_H", "PLAYER_Y", "PLAYER_COLORS",
    "WS_URL", "INPUT_PUBLISH_HZ", "MAX_HP", "MAX_STAMINA", "START_X", "START_DIR",
]
