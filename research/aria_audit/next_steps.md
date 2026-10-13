# ARIA Next Steps & Pilot Execution Roadmap

## 1. Confirmed Blockers

| Blocker ID | Description | Impact | Severity |
| :--- | :--- | :--- | :--- |
| **BLK-01** | **Backend Protocol Mismatch** | ARIA hardcodes Ollama endpoints (`/api/generate`, `/api/tags`). Ollama is not installed. The active local engine is `llama.cpp` (`llama-server`) providing an OpenAI-compatible `/v1/chat/completions` API on port 8081. | **CRITICAL** (Prevents startup) |
| **BLK-02** | **Model Modality Mismatch** | ARIA's perception pipeline (`screen_context.py`) captures screenshot images and expects a Vision-Language Model (`qwen3-vl:2b`). The verified local GGUF model is `qwen2.5-coder-7b-instruct-q4_k_m.gguf`, which is a text-only language model. | **CRITICAL** (Blocks vision loop) |
| **BLK-03** | **Unconstrained Desktop Control** | `ActionRunner` executes raw `pyautogui.click()` and keystrokes on the host OS desktop without coordinate safety clipping, dry-run mode, or VM isolation. | **HIGH** (Safety risk) |
| **BLK-04** | **Unvalidated Action Spec Crash** | `Executor.build_action_spec` calls `next(...)` without error handling, raising uncaught `StopIteration` if the model references a missing or hallucinated `element_id`. | **HIGH** (Reliability blocker) |
| **BLK-05** | **Host Memory Headroom** | Free physical RAM on the Windows 11 host is under 900 MB (~850 MB), though GPU VRAM has ~1.5 GB headroom after loading the 7B model. | **MEDIUM** (Crash / thrashing risk) |

---

## 2. Minimal Required Code Changes (Estimated Effort: 1.5 Days)

To run the proposed research pilot comparing verification vs. non-verification without rewriting the architecture:

1. **Pluggable Backend Adapter in `vlm_client.py` (0.5 day)**:
   * Introduce a configurable provider flag: `ARIA_INFERENCE_BACKEND=llama-server|ollama`.
   * When `llama-server` is active, route chat prompts to `http://127.0.0.1:8081/v1/chat/completions` using the standard OpenAI schema with `response_format={"type": "json_object"}`.
2. **Text-Only Perception Fallback in `screen_context.py` (0.5 day)**:
   * Allow `ScreenContextCollector` to operate in `text_only` mode where perception relies exclusively on the grounded UIA element tree and Win32 window metadata, bypassing image embedding when running text-only models like Qwen2.5-Coder.
3. **Execution Sandboxing & Verification Toggle in `main.py` (0.5 day)**:
   * Add `ARIA_VERIFICATION_ENABLED=0|1`. When disabled (Condition A), the pipeline skips `Verifier.verify` and `Reflector.reflect`, executing planned steps directly.
   * Add a sandboxed ActionRunner mode for filesystem tasks that executes deterministic operations within `research/test_workspace`.

---

## 3. Recommended Pilot Design

* **Model**: Fixed `qwen2.5-coder-7b-instruct-q4_k_m.gguf` on `llama-server` (WSL, CUDA `-ngl 99`, context 2048, temperature 0.0).
* **Sample Size**: 15 deterministic tasks across 3 categories:
  1. Atomic file/directory operations.
  2. Multi-step chained actions with intermediate dependencies.
  3. Adversarial / state-collision scenarios (lock files, missing inputs).
* **Conditions**:
  * **Condition A (Baseline)**: Planner -> Action Runner -> Final Self-Report.
  * **Condition B (Reflective)**: Planner -> Action Runner -> Verifier -> Reflector -> Replan/Done.
* **Oracle Evaluation**: Every run evaluated by automated external assertions checking disk state independently of the model's reported status.

---

## 4. Key Questions Requiring Ryan's Input

1. **Inference Backend Standardization**:
   * Should we standardize on the existing high-performance `llama.cpp` + `llama-server` backend already compiled on the machine, OR is installing Ollama on Windows explicitly required by the project direction?
2. **Perception Strategy**:
   * For the immediate research pilot, should we proceed with a grounded text/UIA accessibility representation using the available Qwen2.5-Coder 7B model, OR should we wait to obtain and test a dedicated multimodal GGUF model (e.g. Qwen2-VL 2B/7B with `mmproj`)?
3. **Desktop Interaction Sandbox**:
   * Does Ryan approve using a dedicated temporary workspace directory for filesystem actions, or is testing against interactive Windows desktop applications (Notepad, Calculator) in an isolated sandbox required?
