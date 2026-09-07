import argparse
import asyncio
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.audio.capture import AudioCapture, AudioCaptureError
from backend.config.loader import load_config


async def dump(seconds: float, out: Path) -> None:
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    cap = AudioCapture(cfg.audio, source="loopback")
    q: asyncio.Queue = asyncio.Queue()
    cap.start(q)
    frames = []
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1)
            except TimeoutError:
                continue
            frames.append(np.frombuffer(chunk.pcm, dtype=np.int16))
    finally:
        cap.stop()
    pcm = np.concatenate(frames) if frames else np.zeros(0, dtype=np.int16)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, pcm, cfg.audio.sample_rate, subtype="PCM_16")
    print(f"wrote {out} samples={len(pcm)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--out", default="data/loopback.wav")
    args = parser.parse_args()
    try:
        asyncio.run(dump(args.seconds, Path(args.out)))
    except AudioCaptureError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
