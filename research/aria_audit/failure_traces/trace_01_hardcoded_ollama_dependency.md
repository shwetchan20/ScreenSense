# Failure Trace 01: Hardcoded Ollama Dependency & Hang

## 1. Initial Conditions
* **Environment**: Windows 11 host with Python 3.13 virtual environment (`.venv`).
* **Runtime Target**: `src/aria/main.py` CLI invoked with `--observe --observe-cycles 1` or `tests/test_smoke.py`.
* **Configuration State**:
  * `OLLAMA_URL`: `http://localhost:11434` (from `src/aria/config.py`).
  * `VLM_MODEL`: `qwen3-vl:2b`.
  * `ARIA_VLM_TIMEOUT_SECONDS`: `180` (default).
* **Local Backend Available**: `llama.cpp` (`llama-server`) running in WSL 2 on port `8081`, with `qwen2.5-coder-7b-instruct-q4_k_m.gguf`. Ollama service is not installed on Windows host.

## 2. Relevant Observation & Context
When ARIA starts, `AriaRuntime.__init__` instantiates:
```python
self._vlm = VLMClient(ollama_url=f"{OLLAMA_URL}/api/generate", model=VLM_MODEL)
self._screen = ScreenContextCollector(vlm=self._vlm)
```
Upon running the observe loop (`run_observe`), `ScreenContextCollector.get_unified_screen_context()` triggers:
```python
vlm_task = asyncio.create_task(self.get_vlm_context(image_bytes))
```
which executes `VLMClient.generate_text()` targeting `http://localhost:11434/api/generate`.

## 3. Model Output
None. The HTTP client fails to connect to port 11434.

## 4. Action Sequence & Empirical Reproduction
Command executed:
```powershell
.\.venv\Scripts\python.exe -c "import asyncio, os; os.environ['ARIA_VLM_TIMEOUT_SECONDS']='2'; from aria.perception.vlm_client import VLMClient; v = VLMClient(ollama_url='http://localhost:11434/api/generate', model='qwen3-vl:2b'); asyncio.run(v.generate_json('hi'))"
```

Observed Traceback:
```text
Traceback (most recent call last):
  File "C:\Users\shwet k\OneDrive\Desktop\screensense\.venv\Lib\site-packages\httpcore\_backends\anyio.py", line 113, in connect_tcp
    with map_exceptions(exc_map):
  File "C:\Users\shwet k\OneDrive\Desktop\screensense\.venv\Lib\site-packages\httpcore\_exceptions.py", line 14, in map_exceptions
    raise to_exc(exc) from exc
httpcore.ConnectTimeout

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\shwet k\OneDrive\Desktop\screensense\src\aria\perception\vlm_client.py", line 49, in generate_json
    response = await client.post(self._url, json=payload)
  ...
  File "C:\Users\shwet k\OneDrive\Desktop\screensense\.venv\Lib\site-packages\httpx\_transports\default.py", line 118, in map_httpcore_exceptions
    raise mapped_exc(message) from exc
httpx.ConnectTimeout
```

## 5. Actual Outcome
Process blocked. In default execution (`ARIA_VLM_TIMEOUT_SECONDS=180` with 3 retries), the pipeline blocks for up to 540 seconds without ever producing an action or perception summary. When executed under test suite (`tests/test_smoke.py`), tests hang up to 600 seconds until aborted.

## 6. Agent-Reported Outcome
Unreported / unhandled hanging process.

## 7. Independent Verifier Result
`FAIL` (Oracle check: Runtime failed to initialize; zero perception outputs generated).

## 8. Failure Classification
* **Primary Label**: `J_TIMEOUT_RESOURCE_EXHAUSTION`
* **Secondary Label**: `A_PERCEPTION_FAILURE`

## 9. Why This Trace Matters
ARIA lacks backend abstraction. While the machine possesses a fully functional, GPU-accelerated local inference backend (`llama.cpp` serving a 7B model on port 8081), ARIA cannot utilize it because it hardcodes Ollama-specific API endpoints (`/api/generate`) and fails to detect backend unavailability gracefully.
