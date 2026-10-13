# Reproduction Guide: ARIA Audit & Local Inference Feasibility

## 1. Prerequisites & Environment

* **Host Operating System**: Microsoft Windows 11 (tested on Version 10.0.26300).
* **WSL 2**: Ubuntu distribution installed and running (`wsl -l -v`).
* **Hardware Requirements**:
  * NVIDIA GPU with >= 6 GB VRAM (tested on NVIDIA GeForce RTX 4050 Laptop GPU, Driver 592.82, CUDA 13.1).
  * System RAM >= 16 GB.
* **Python Runtime**:
  * Python 3.13.7 located in `c:\Users\shwet k\OneDrive\Desktop\screensense\.venv`.

---

## 2. Launching Local Inference Backend (`llama.cpp`)

The local inference backend resides inside WSL Ubuntu, compiled with CUDA acceleration.

### Step 1: Start `llama-server` in WSL
Run from PowerShell in the workspace root:
```powershell
wsl -e bash -c "LD_LIBRARY_PATH=/home/shwet/llm/build/bin /home/shwet/llm/build/bin/llama-server -m /home/shwet/llm/models/qwen2.5-coder-7b-instruct-q4_k_m.gguf --port 8081 -ngl 99 -c 2048 --host 0.0.0.0"
```

### Step 2: Verify Server Health from Windows
In a separate PowerShell prompt:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8081/health" -Method GET
```
**Expected Response:**
```json
{"status": "ok"}
```

### Step 3: Verify GPU Offloading and VRAM Allocation
Run:
```powershell
nvidia-smi
```
**Expected Result:**
VRAM usage will increase from baseline (~111 MiB) to **~4571 MiB / 6141 MiB**, confirming 100% offload of the Q4_K_M 7B model.

### Step 4: Verify Local JSON Chat Completion Latency
Execute:
```powershell
$body = @{
    messages = @(
        @{ role = "user"; content = "Return JSON only: {`"status`": `"success`", `"answer`": 42}" }
    )
    temperature = 0.0
    response_format = @{ type = "json_object" }
} | ConvertTo-Json -Depth 5

Measure-Command {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:8081/v1/chat/completions" -Method POST -Body $body -ContentType "application/json"
}
$response.choices[0].message.content
```
**Expected Output:**
Latency ~1.1 to 1.3 seconds; returns valid JSON object.

---

## 3. How to Reset the Disposable Test Workspace

Before executing any benchmark run:
```powershell
$testDir = "c:\Users\shwet k\OneDrive\Desktop\screensense\research\test_workspace"
if (Test-Path $testDir) {
    Remove-Item -Path $testDir -Recurse -Force
}
New-Item -ItemType Directory -Path $testDir -Force
```

---

## 4. How to Inspect ARIA State & Existing Tests

### Run Existing Smoke Test (Demonstrates Unreachable Port 11434 Hang)
```powershell
$env:ARIA_VLM_TIMEOUT_SECONDS = "5"
.\.venv\Scripts\pytest.exe tests/test_smoke.py -v
```
*Note: This test is designed to verify Ollama on port 11434. In the audited state without Ollama, tests will fail or time out after 5 seconds.*

---

## 5. Known Limitations & Nondeterminism

1. **WSL Inter-Process Networking**: Windows connects to WSL via virtual loopback adapter (`127.0.0.1`). If Windows Firewall or a third-party antivirus blocks loopback connections, bind `llama-server` to `0.0.0.0` or WSL IP.
2. **Context Window Constraint**: `num_ctx` in ARIA's `.env.example` defaults to 1024 tokens. If desktop accessibility trees exceed 1024 tokens, generation will truncate.
3. **Desktop Interaction Concurrency**: Running real `pyautogui` clicks without mouse isolation can interfere with active user windows. All automated runs must use mocked or sandboxed targets.
