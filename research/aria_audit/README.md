# ARIA Research Readiness Audit

This directory contains the complete, auditable research readiness report, environmental benchmarks, architecture analysis, and pilot experiment design for the ARIA desktop agent project.

## Directory Structure

* **`audit_report.md`**: Master audit report containing executive summary, startup status, feasibility analysis, and findings.
* **`architecture.md`**: Detailed technical reconstruction of ARIA's perception, planning, execution, verification, and reflection pipeline.
* **`environment.json`**: Machine hardware, OS version, GPU VRAM, Python environment, and local `llama.cpp` inference telemetry.
* **`task_manifest.json`**: Standardized definitions for five diagnostic tasks with independent ground-truth verification procedures.
* **`logging_schema.json`**: JSON Schema specification for collecting structured trial data across future pilot runs.
* **`pilot_results.csv`**: Experimental results table for baseline feasibility tests and diagnostic status.
* **`failure_traces/`**:
  * `trace_01_hardcoded_ollama_dependency.md`: Analysis of the connection hang caused by hardcoded Ollama endpoints.
  * `trace_02_action_runner_missing_element.md`: Analysis of the unhandled `StopIteration` crash during action execution.
* **`reproduction.md`**: Step-by-step instructions to reproduce the local `llama.cpp` GPU environment and validation tests.
* **`next_steps.md`**: Roadmap of confirmed blockers, minimal required code changes (1.5 days effort), and key design decisions for Ryan.
