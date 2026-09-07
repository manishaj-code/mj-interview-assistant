import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.audio.capture import AudioCapture
from backend.config.loader import load_config
from backend.context.context_manager import ContextManager
from backend.detection.question_detector import QuestionDetector
from backend.llm.claude_client import ClaudeClient, LlmError, has_llm_key, select_transport
from backend.stt.transcriber import Transcriber


async def _run(resume: str, jd: str) -> None:
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    queue: asyncio.Queue = asyncio.Queue()
    cap = AudioCapture(cfg.audio, source="loopback")
    tr = Transcriber(cfg.stt, engine_impl="auto")
    detector = QuestionDetector(cfg.question_detection)
    context = ContextManager(cfg.context, cfg.llm.answer_style)
    if resume:
        context.set_resume(resume)
    if jd:
        context.set_job_description(jd)
    elif cfg.context.job_description:
        context.set_job_description(cfg.context.job_description)
    transport, api_key = select_transport(cfg.groq_api_key, cfg.gemini_api_key, cfg.anthropic_api_key)
    client = ClaudeClient(cfg.llm, api_key, transport)

    await tr.start()
    cap.start(queue)
    print("listening for questions. Ctrl+C to stop.", flush=True)

    async def handle(detected) -> None:
        print(f"\nQ: {detected.question_text}", flush=True)
        messages = context.build_messages(detected.question_text)
        parts: list[str] = []
        try:
            async for token in client.stream_answer(context.system_prompt, messages):
                print(token, end="", flush=True)
                parts.append(token)
        except LlmError as exc:
            print(f"\n{exc.code}: {exc.message}", flush=True)
            return
        print(flush=True)
        context.add_qa_pair(detected.question_text, "".join(parts))

    async def ticker() -> None:
        while True:
            await asyncio.sleep(0.05)
            detected = detector.on_silence(int(time.time() * 1000))
            if detected:
                await handle(detected)

    async def audio() -> None:
        while True:
            chunk = await queue.get()
            event = await tr.process_chunk(chunk)
            if event is None:
                continue
            detector.on_transcript(event)

    try:
        await asyncio.gather(ticker(), audio())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        cap.stop()
        await tr.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", default="")
    parser.add_argument("--jd", default="")
    args = parser.parse_args()
    cfg = load_config(Path("backend/config/defaults.json"), Path("data/config.json"), Path(".env"))
    if not has_llm_key(cfg.groq_api_key, cfg.gemini_api_key, cfg.anthropic_api_key):
        print("MISSING_API_KEY", file=sys.stderr)
        sys.exit(2)
    asyncio.run(_run(args.resume, args.jd))


if __name__ == "__main__":
    main()
