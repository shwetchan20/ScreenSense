"""Quick smoke test: VLMClient -> llama-server -> JSON round-trip."""
import asyncio
import os
import time

os.environ["ARIA_INFERENCE_BACKEND"] = "llama-server"
os.environ["ARIA_LLAMA_SERVER_URL"] = "http://127.0.0.1:8081/v1/chat/completions"
os.environ["ARIA_LLAMA_MODEL"] = "qwen2.5-coder-7b-instruct-q4_k_m"
os.environ["ARIA_VLM_TIMEOUT_SECONDS"] = "30"
os.environ["ARIA_VLM_MAX_RETRIES"] = "2"

# Must set before importing aria modules
import sys
sys.path.insert(0, "src")

from aria.perception.vlm_client import VLMClient


async def main() -> None:
    client = VLMClient()
    print(f"[INFO] backend={client._backend}, url={client._llama_url}, model={client._model}")

    prompt = 'Return ONLY valid JSON: {"status": "ok", "backend": "llama-server"}'
    t0 = time.perf_counter()
    result = await client.generate_json(prompt)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    print(f"[PASS] JSON round-trip in {elapsed_ms}ms: {result}")

    prompt2 = "Say hello in one sentence."
    t1 = time.perf_counter()
    text = await client.generate_text(prompt2, num_predict=32)
    elapsed2_ms = int((time.perf_counter() - t1) * 1000)
    print(f"[PASS] Text generation in {elapsed2_ms}ms: {text[:80]!r}")


asyncio.run(main())
