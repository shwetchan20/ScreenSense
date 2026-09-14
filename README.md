# ScreenSense

> A local-first proactive AI copilot for Windows that understands what is happening on your screen and decides when assistance is actually useful.

ScreenSense is an experimental desktop AI system built around **perception, reasoning, memory, and controlled action**.

Instead of waiting for a user to send a prompt, ScreenSense continuously monitors meaningful changes in the active desktop context, evaluates whether the change requires attention, and can offer assistance when confidence and relevance are high.

The project is designed around one principle:

**An AI assistant should know when *not* to interrupt.**

---

## Why ScreenSense?

Most desktop AI assistants follow:

```text
User → Prompt → AI → Response
```

ScreenSense explores a different interaction model:

```text
Desktop
   ↓
Perception
   ↓
Change Detection
   ↓
Context / Vision Analysis
   ↓
Confidence + Impact Gating
   ↓
Should I Interrupt?
   ↓
User Confirmation
   ↓
Action / Response
   ↓
Memory + Audit Log
```

The difficult part is not calling an LLM.

The difficult part is deciding **when an observation is meaningful enough to justify an interruption or action**.

---

## Core Capabilities

### Perception

* Periodic screen capture using `mss`
* Configurable frame-difference detection
* Active-window awareness
* Optional OCR context
* Focus-mode and application blocklists

### AI Reasoning

* Vision-based screen understanding
* Local LLM inference through Ollama
* Optional Gemini escalation
* Hybrid local-first reasoning
* Structured reasoning outputs
* Confidence-based decision making

### Proactive Assistance

* Idle/typing detection
* Confidence gating
* Impact-based interruption scoring
* Cooldowns
* Semantic deduplication
* Stale-decision protection

### Agent System

ScreenSense uses a coordinator with specialized agent capabilities:

```text
                    ┌───────────────┐
                    │   ScreenSense │
                    │   Coordinator │
                    └───────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
       Code Agent      Browse Agent     General Agent
                            │
                       Translate Agent
```

The agent runtime is designed to support controlled multi-step actions rather than unrestricted autonomous execution.

---

## Safety Architecture

ScreenSense is intentionally **human-in-the-loop**.

Actions can pass through:

```text
Observation
    ↓
Reasoning
    ↓
Action Proposal
    ↓
Preview
    ↓
User Confirmation
    ↓
Allowlist / Safety Policy
    ↓
Execution
    ↓
Verification
    ↓
Audit Log
```

The system also supports:

* Action allowlists
* Confirmation before execution
* Per-step action auditing
* Verification hooks
* Cooldowns
* Circuit breakers
* Remote approval through Telegram
* Observe-only operation

The default philosophy is:

> **Observe first. Ask before acting. Verify after acting.**

---

## Hybrid Local + Cloud Reasoning

ScreenSense can operate entirely with a local model or use a hybrid architecture.

### Local

```text
Screen → Local Vision/LLM → Decision
```

### Hybrid

```text
Screen
   ↓
Local Qwen
   ↓
Confidence sufficient?
   ├── Yes → Decision
   └── No  → Gemini escalation
                  ↓
               Decision
```

This allows inexpensive local inference for routine situations while reserving cloud reasoning for cases that require stronger analysis.

Example configuration:

```env
REASONING_MODE=hybrid
LOCAL_LLM_PROVIDER=ollama
LOCAL_LLM_MODEL=qwen2.5:latest
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
LOCAL_LLM_USE_VISION=true
```

Supported modes:

* `local` — local model only
* `hybrid` — local model with cloud escalation
* `gemini` — Gemini-based reasoning

---

## Memory

ScreenSense maintains rolling context and can persist runtime information through configurable storage backends.

Current persistence abstractions support:

* Local storage
* Firestore
* Dual local + Firestore mode

The system can also adapt interruption behaviour based on user interaction and application context.

---

## Voice

ScreenSense includes an optional voice layer with multiple providers:

* Edge TTS
* Piper
* Coqui XTTS
* pyttsx3

Voice behaviour can be configured for different interruption styles and personas.

Voice functionality is treated as an interface around the core agent system rather than being coupled to the reasoning pipeline.

---

## Observability

Every important action can produce structured audit information.

Example:

```text
Observation
    ↓
Decision
    ↓
Interruption
    ↓
Action
    ↓
Verification
```

These events can be recorded as JSONL logs for debugging, evaluation, and future policy tuning.

This is important because proactive systems need to answer:

**Why did the assistant interrupt me?**

---

## Project Structure

```text
ScreenSense/
├── src/
│   └── screensense/
│       ├── perception/
│       ├── agents/
│       ├── reasoning/
│       ├── actions/
│       ├── memory/
│       └── ...
│
├── tests/
├── docs/
├── scripts/
├── .env.example
├── pyproject.toml
└── README.md
```

The implementation is still evolving, so module boundaries may change as the architecture is refined.

---

## Quick Start

### Requirements

* Windows
* Python 3.11+
* Ollama — optional for local reasoning
* Gemini API key — optional for cloud/hybrid reasoning

### Installation

```powershell
git clone https://github.com/shwetchan20/ScreenSense.git
cd ScreenSense

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"
```

Create the environment file:

```powershell
Copy-Item .env.example .env
```

For local-only operation, a Gemini API key is not required.

Run:

```powershell
python -m screensense.app
```

---

## Local LLM Setup

For local-first reasoning, install and run Ollama and configure:

```env
REASONING_MODE=local
LOCAL_LLM_PROVIDER=ollama
LOCAL_LLM_MODEL=qwen2.5:latest
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434
```

For a vision-capable model, use an appropriate vision model supported by your local hardware.

---

## Optional Components

ScreenSense contains optional integrations for:

| Component     | Purpose                         |
| ------------- | ------------------------------- |
| Ollama        | Local LLM/VLM inference         |
| Gemini        | Cloud reasoning / escalation    |
| OCR           | Additional visible-text context |
| Telegram      | Remote action approval          |
| Firestore     | Persistent memory/audit storage |
| TTS providers | Voice interaction               |
| Cloud Run     | Optional backend deployment     |

These components are not required for the core perception and reasoning architecture.

---

## Current Status

**Experimental / active development**

The core architecture is functional, but ScreenSense is **not presented as a finished production application**.

Some components are experimental, incomplete, or still being redesigned.

Current development priorities:

* Improve perception reliability
* Reduce unnecessary interruptions
* Improve local VLM performance
* Strengthen action verification
* Improve memory quality
* Simplify the runtime architecture
* Expand automated evaluation
* Improve Windows UX

---

## Roadmap

### Perception

* [x] Screen capture
* [x] Frame-change detection
* [x] Active-window awareness
* [x] Optional OCR
* [ ] Stronger semantic scene understanding
* [ ] Better temporal reasoning

### Reasoning

* [x] Vision reasoning
* [x] Local LLM support
* [x] Hybrid reasoning
* [x] Confidence gating
* [ ] Better evaluation benchmarks
* [ ] Improved hallucination detection

### Agents

* [x] Agent coordinator
* [x] Specialized agent routing
* [x] Action proposals
* [x] Human confirmation
* [x] Action auditing
* [ ] More robust multi-step execution

### Memory

* [x] Rolling context
* [x] Persistence abstraction
* [x] User preference adaptation
* [ ] Long-term memory evaluation

### Safety

* [x] Confirmation gates
* [x] Action allowlists
* [x] Cooldowns
* [x] Circuit breakers
* [x] Audit logging
* [ ] Formal policy evaluation

---

## Design Principles

ScreenSense is being developed around a few constraints:

1. **Local-first where practical**
2. **Minimize unnecessary cloud inference**
3. **Do not interrupt without sufficient evidence**
4. **Never silently execute high-impact actions**
5. **Keep perception, reasoning, and execution separable**
6. **Record enough information to explain system decisions**
7. **Treat autonomy as a controlled capability, not a default**

---

## Limitations

ScreenSense is an experimental research/engineering project.

It currently has limitations around:

* Vision-model latency
* False-positive and false-negative perception
* Windows-specific behaviour
* Local model resource requirements
* Agent reliability
* Long-term memory quality
* Voice and UI integrations
* Autonomous action robustness

These are active engineering problems rather than claims of production readiness.

---

## Why This Project Exists

ScreenSense is an exploration of what happens when an AI assistant moves from:

> **"Ask me anything."**

to:

> **"I understand enough of your current context to know when I might be useful."**

The project combines several areas I am interested in:

* Multimodal AI
* Vision-language models
* Agentic systems
* Local LLM inference
* Context and memory
* Human-AI interaction
* AI safety and action verification

---

