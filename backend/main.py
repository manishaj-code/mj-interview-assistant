import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config.loader import load_config
from backend.pipeline import Pipeline
from backend.server.ws_server import WsServer
from backend.storage.session_store import SessionStore


def _defaults_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "config" / "defaults.json"
    return Path("backend/config/defaults.json")


def _user_data() -> Path:
    path = Path(os.environ.get("AIA_USER_DATA", "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _env_path(user_data: Path) -> Path:
    nested = user_data / ".env"
    if nested.exists():
        return nested
    return Path(".env")


def _history_path(cfg, user_data: Path) -> str:
    hist = Path(cfg.storage.session_history_path)
    if hist.is_absolute():
        return str(hist)
    return str(user_data / hist.name)


async def main() -> None:
    user_data = _user_data()
    cfg = load_config(_defaults_path(), user_data / "config.json", _env_path(user_data))
    level = getattr(logging, cfg.log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    store = SessionStore(_history_path(cfg, user_data), cfg.storage.session_history_enabled)
    server = WsServer(cfg.server.host, cfg.server.port, pipeline=None)

    async def broadcast(msg):
        await server.broadcast(msg)

    pipeline = Pipeline(cfg, broadcast, store)
    server.pipeline = pipeline
    await server.start()
    logging.info("websocket listening on ws://%s:%s", cfg.server.host, cfg.server.port)
    try:
        await asyncio.Future()
    finally:
        await pipeline.stop_listening()
        await server.stop()
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
