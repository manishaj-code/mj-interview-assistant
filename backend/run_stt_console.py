import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.audio.capture import AudioCapture
from backend.config.loader import load_config
from backend.stt.transcriber import Transcriber


async def main() -> None:
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    q: asyncio.Queue = asyncio.Queue()
    cap = AudioCapture(cfg.audio, source="loopback")
    tr = Transcriber(cfg.stt, engine_impl="auto")
    await tr.start()
    cap.start(q)
    print("listening. Ctrl+C to stop.", flush=True)
    try:
        while True:
            chunk = await q.get()
            ev = await tr.process_chunk(chunk)
            if ev is None:
                continue
            tag = "FINAL" if ev.is_final else "PARTIAL"
            print(f"{tag}: {ev.text}", flush=True)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        cap.stop()
        await tr.stop()


if __name__ == "__main__":
    asyncio.run(main())
