# Spell Blade Match Coordinator — server-only image (pygame-free / no SDL).
# Only the headless coordinator is deployed; the pygame clients run on laptops
# and connect out to this service's public wss:// URL.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# The ONLY dependency set installed into the image (must stay pygame-free).
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Pygame-free server packages only — no client modules, no assets, no SDL.
COPY coordinator/ ./coordinator/
COPY messaging/ ./messaging/
COPY audit/ ./audit/

# Cosmetic; Railway injects $PORT and run_server reads it at runtime.
EXPOSE 8000

CMD ["python", "-m", "coordinator.run_server"]
