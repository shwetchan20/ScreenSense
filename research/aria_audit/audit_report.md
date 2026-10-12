# ARIA Research Readiness Audit Report

**Audit Date**: October 13, 2026  
**Auditor**: Antigravity Research Engineering  
**Target Repository**: `screensense` / `ARIA` (`c:\Users\shwet k\OneDrive\Desktop\screensense`)  
**Audited Commit**: `5d97ca41532fb578f03d2547f472ec7c636dc3ad` (Branch: `main`, Working Tree: modified/restructured)

---

## 1. Executive Summary

An audit of the ARIA desktop agent project was conducted to determine whether it can support a reproducible investigation of local desktop agent reliability, failure detection, and the impact of verification/reflection.

**Primary Finding**:  
The audited repository contains an architectural framework for multi-step planning, execution, verification, and reflection (`src/aria/`), but **cannot start or run in its current state** due to two immediate structural blockers:
1. **Inference Backend Disconnect**: ARIA's code hardcodes communication with Ollama at `http://localhost:11434/api/generate` expecting a vision-language model (`qwen3-vl:2b`). However, **Ollama is not installed or available** on the host.
2. **Local Backend Feasibility**: An alternative local inference backend—**`llama.cpp` (`llama-server`)**—is installed, fully compiled with CUDA support inside WSL 2, and successfully validated during this audit. It runs a 7B parameter GGUF model (`qwen2.5-coder-7b-instruct-q4_k_m.gguf`) with 100% GPU offload on the local NVIDIA RTX 4050 GPU, delivering fast, deterministic inference (**1.15 seconds per JSON completion**; 24 tokens/sec). However, this model is **text/code only**, and ARIA lacks an adapter to connect to `llama-server`.

Until a minimal adapter bridge is added and desktop interactions are constrained to a disposable test workspace, automated benchmark tasks cannot safely or reliably execute.

---

## 2. Hardware and Model Specifications

### Host Machine Specifications
* **Operating System**: Microsoft Windows 11 Home Single Language (Build 10.0.26300).
* **CPU**: 13th Gen Intel(R) Core(TM) i5-13420H (8 physical cores, 12 logical processors).
* **RAM**: 16.0 GB total visible; **850 MB free** (indicates severe host memory pressure).
* **GPU**: NVIDIA GeForce RTX 4050 Laptop GPU (6,141 MiB VRAM total, Driver 592.82, CUDA 13.1).
* **Integrated GPU**: Intel(R) UHD Graphics (2.0 GB shared).
* **Python Runtime**: Python 3.13.7 within `.venv`.

### Local Inference Engine: `llama.cpp`
* **Subsystem**: WSL 2 (Ubuntu distribution).
* **Binaries**: `/home/shwet/llm/build/bin/llama-server` and `llama-cli`.
* **Version**: `0.5.0-dev (build 11153, commit 9710a3217)`, compiled with GNU 13.3.0 and CUDA (`libggml-cuda.so.0.25.1`).
* **Available Model**: `/home/shwet/llm/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf`.
  * Family: Qwen2.5-Coder.
  * Size: 4.68 GB (4,683,073,536 bytes).
  * Quantization: `Q4_K_M`.
  * Modality: **Text-only** (No vision encoder weights).
* **Offloading Performance**:
  * With `-ngl 99`, all 29 layers are offloaded to the RTX 4050 GPU.
  * VRAM consumption: **4,571 MiB / 6,141 MiB** (leaving ~1.5 GB headroom).
  * Model load latency: **3.99 seconds**.
  * Inference generation rate: **24.0 tokens/second** (prompt eval: 157.8 t/s).
  * Round-trip JSON chat completion latency: **1,148 ms** (1.15s).
  * Cloud fallback: **Zero**. Inference is 100% local and private.

---

## 3. Architecture & Execution Trace

The core execution path is defined in `src/aria/main.py`:
1. **Trigger & Perception**: Captures screen frame (`mss`), extracts UI Automation elements (`uiautomation`), and enumerates top-level windows (`win32gui`). Passes screenshot bytes to `VLMClient.generate_text()`.
2. **Classification**: `Classifier.classify()` categorizes the user prompt into `screen_task`, `conversation`, or `memory_query`.
3. **Planning**: `Planner.plan()` requests a multi-step plan array (`{"steps": [{"step": 1, "action": "click", "element_id": ...}]}`).
4. **Execution**: `Executor.build_action_spec()` resolves element coordinates and dispatches to `ActionRunner.run()`, which invokes raw `pyautogui` clicks, hotkeys, or typing.
5. **Verification**: `Verifier.verify()` prompts the model with pre-action context, post-action context, and post-action screenshot to produce `{"success": true|false, "observation": "..."}`.
6. **Reflection**: `Reflector.reflect()` evaluates the step and outputs one of four decisions: `next_step`, `replan`, `done`, or `abort`.

### Critical Architectural Vulnerabilities Identified
1. **No External Grounding**: ARIA's verifier is an ungrounded secondary call to the same LLM/VLM. If the model hallucinates success or misreads the screenshot, the agent records the task as completed without verifying external file or operating system state.
2. **StopIteration Crash on Hallucinated Elements**: In `src/aria/agent/executor.py`, `next(e for e in elements if int(e["id"]) == element_id)` lacks a fallback. If the model proposes an element ID not present in the current UIA list, the entire process crashes immediately.
3. **1024 Token Context Window**: `ARIA_VLM_NUM_CTX` is configured to 1024 tokens. Real desktop accessibility trees frequently exceed 1,000 tokens, risking silent prompt truncation during multi-step planning.

---

## 4. Startup & Execution Status

| Component | Tested Action | Observed Result | Status |
| :--- | :--- | :--- | :--- |
| **Existing Smoke Test** | `pytest tests/test_smoke.py` | Hangs for 600s attempting to reach `http://localhost:11434`. | **FAILED** |
| **Observe Mode** | `python -m aria.main --observe` | Hangs on `vlm_task` in `ScreenContextCollector`. | **FAILED** |
| **llama-server Backend** | `Invoke-RestMethod http://127.0.0.1:8081/health` | Returns `status: ok` in 12ms. | **VERIFIED** |
| **llama-server JSON Inference** | POST `/v1/chat/completions` | Returns valid JSON completion in 1.15s. | **VERIFIED** |
| **GPU Offloading** | `nvidia-smi` | Allocates 4,571 MiB on RTX 4050 GPU. | **VERIFIED** |

---

## 5. Diagnostic Tasks Assessment (Phase E)

Because the unmodified ARIA codebase hardcodes Ollama's API (`/api/generate`) and fails to start without it, none of the exploratory diagnostic tasks could be executed end-to-end without modifying code. In compliance with Rule 11 (*"Label every unexecuted test as NOT RUN"*), all five diagnostic tasks are recorded as **NOT RUN**:

* **TASK 1 (Basic file execution)**: NOT RUN (Blocked by backend API mismatch).
* **TASK 2 (Multi-step directory + file execution)**: NOT RUN (Blocked by backend API mismatch).
* **TASK 3 (Context retention across steps)**: NOT RUN (Blocked by backend API mismatch).
* **TASK 4 (Unexpected state change adaptation)**: NOT RUN (Blocked by backend API mismatch).
* **TASK 5 (Missing parameter abstention)**: NOT RUN (Blocked by backend API mismatch).

---

## 6. Safety Concerns

1. **Unrestricted Mouse and Keyboard Control**: `ActionRunner` invokes `pyautogui` directly against the user's live desktop. In an unconstrained environment, errant model clicks could target production windows, browser tabs, or system files.
2. **Lack of Coordinate Bounds**: `pyautogui.click()` is called with model-derived coordinates without clipping to a bounding box or checking whether the window has focus.
3. **High Memory Pressure**: Free RAM is ~850 MB. Running unconstrained background processes risks host memory exhaustion (OOM paging / freezes).

---

## 7. Research Feasibility Assessment

### Can ARIA support a reproducible investigation of local desktop agent reliability?
**Yes, but ONLY after resolving two narrow interface bottlenecks**:
1. **Protocol Bridge**: Implement an adapter in `vlm_client.py` allowing ARIA to communicate with `llama-server`'s OpenAI-compatible endpoint on port 8081.
2. **Text-Grounded Perception**: Enable a text-only reasoning path that uses the rich UIA accessibility tree and Win32 metadata instead of requiring image embeddings, matching the available `Qwen2.5-Coder 7B` model.
3. **Condition A vs. Condition B Isolation**: The codebase already separates `Verifier` and `Reflector` as modular classes in `src/aria/agent/`. By introducing an environment flag (`ARIA_ENABLE_VERIFICATION=1|0`) in `AriaRuntime._run_screen_task()`, the pilot can cleanly toggle verification/reflection while keeping the model, prompt, generation settings, and tools strictly identical.

---

## 8. Summary of Created Audit Artifacts

All 11 research deliverables have been generated in the isolated audit directory:
* [README.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/README.md): Overview and navigation guide.
* [audit_report.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/audit_report.md): This comprehensive audit report.
* [architecture.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/architecture.md): Component breakdown and verification analysis.
* [environment.json](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/environment.json): Machine hardware, software, and inference telemetry.
* [task_manifest.json](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/task_manifest.json): Specification of the 5 diagnostic tasks with independent oracle verifications.
* [logging_schema.json](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/logging_schema.json): Standardized JSON schema for recording research runs.
* [pilot_results.csv](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/pilot_results.csv): Results table tracking experimental runs and blocker status.
* [trace_01_hardcoded_ollama_dependency.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/failure_traces/trace_01_hardcoded_ollama_dependency.md): Failure trace on Ollama connection hang.
* [trace_02_action_runner_missing_element.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/failure_traces/trace_02_action_runner_missing_element.md): Failure trace on unvalidated element ID crash.
* [reproduction.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/reproduction.md): Step-by-step reproduction guide.
* [next_steps.md](file:///c:/Users/shwet%20k/OneDrive/Desktop/screensense/research/aria_audit/next_steps.md): Blockers, estimated effort, and decision questions for project leadership.

---

## 9. Integration Status Update (October 13, 2026)

**BLK-01 (Backend Protocol Mismatch): RESOLVED**

The minimal adapter bridge has been implemented and verified without replacing the existing architecture:

| File | Change | Status |
| :--- | :--- | :--- |
| src/aria/config.py | Added INFERENCE_BACKEND, LLAMA_SERVER_URL, LLAMA_MODEL, ENABLE_VERIFICATION, SANDBOX_WORKSPACE, PERCEPTION_MODE | Applied |
| src/aria/perception/vlm_client.py | Added llama-server branch routing to /v1/chat/completions with 
esponse_format=json_object | Applied |
| src/aria/agent/executor.py | Fixed StopIteration crash (BLK-04): guarded next() + element_id_missing flag | Applied |
| src/aria/main.py | Backend-conditional VLMClient init; health check pings llama-server /health | Applied |
| .env | Switched to ARIA_INFERENCE_BACKEND=llama-server, ARIA_PERCEPTION_MODE=text_grounded, context 2048, timeout 30s | Applied |

**Pipeline Integration Test Results (research/test_pipeline_integration.py): 5/5 PASS**

| Test | Result | Latency |
| :--- | :--- | :--- |
| backend_health_json | PASS | 1789 ms |
| classifier_screen_task | PASS | 1789 ms |
| classifier_conversation | PASS | 1213 ms |
| planner_file_task (2 steps returned) | PASS | 5594 ms |
| planner_ambiguous_task | PASS | 2356 ms |

**BLK-01 and BLK-04 are closed. BLK-02 is mitigated via text_grounded perception mode.**

**Next Action**: Execute TASK-01 through TASK-05 from task_manifest.json against the live ARIA pipeline under Condition A then Condition B.
