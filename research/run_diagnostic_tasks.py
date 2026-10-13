"""
ARIA Diagnostic Task Harness
=============================
Executes the five tasks defined in task_manifest.json through the real ARIA
pipeline (Classifier -> Planner -> Executor -> ActionRunner, optionally
Verifier -> Reflector).

Design constraints
------------------
* No task is ever recorded as SUCCESS unless the independent filesystem oracle
  confirms it.  ARIA's self-reported status is recorded separately.
* Each task resets the test workspace to its exact initial_state before running.
* Failures are evidence, not errors — they are logged and execution continues.
* No pyautogui / live desktop actions (ARIA_SANDBOX_MODE=1 is enforced).
* All output is written to research/aria_audit/runs/<run_id>/ as JSONL and CSV.

Usage
-----
Run Condition A (no verification):
    .venv\\Scripts\\python.exe research\\run_diagnostic_tasks.py --condition A

Run Condition B (verification + reflection):
    .venv\\Scripts\\python.exe research\\run_diagnostic_tasks.py --condition B

Run a single task:
    .venv\\Scripts\\python.exe research\\run_diagnostic_tasks.py --condition A --task TASK-01

Dry-run (plan only, no execution):
    .venv\\Scripts\\python.exe research\\run_diagnostic_tasks.py --condition A --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Must set before aria imports ─────────────────────────────────────────────
os.environ.setdefault("ARIA_INFERENCE_BACKEND", "llama-server")
os.environ.setdefault("ARIA_LLAMA_SERVER_URL", "http://127.0.0.1:8081/v1/chat/completions")
os.environ.setdefault("ARIA_LLAMA_MODEL", "qwen2.5-coder-7b-instruct-q4_k_m")
os.environ.setdefault("ARIA_VLM_TIMEOUT_SECONDS", "30")
os.environ.setdefault("ARIA_VLM_MAX_RETRIES", "2")
os.environ.setdefault("ARIA_VLM_NUM_CTX", "2048")
os.environ.setdefault("ARIA_PERCEPTION_MODE", "text_grounded")
os.environ.setdefault("ARIA_SANDBOX_MODE", "1")   # no live pyautogui ever
os.environ.setdefault("ARIA_SANDBOX_WORKSPACE", "research/test_workspace")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from aria.agent.action_runner import ActionRunner   # noqa: E402
from aria.agent.classifier import Classifier        # noqa: E402
from aria.agent.executor import Executor            # noqa: E402
from aria.agent.planner import Planner              # noqa: E402
from aria.agent.reflector import Reflector          # noqa: E402
from aria.agent.verifier import Verifier            # noqa: E402
from aria.perception.vlm_client import VLMClient    # noqa: E402

# ── Paths ────────────────────────────────────────────────────────────────────
WORKSPACE = REPO_ROOT / "research" / "test_workspace"
MANIFEST_PATH = REPO_ROOT / "research" / "aria_audit" / "task_manifest.json"
RUNS_DIR = REPO_ROOT / "research" / "aria_audit" / "runs"
PILOT_CSV = REPO_ROOT / "research" / "aria_audit" / "pilot_results.csv"

# ── Constants ────────────────────────────────────────────────────────────────
GIT_COMMIT = subprocess.check_output(
    ["git", "rev-parse", "--short", "HEAD"],
    cwd=str(REPO_ROOT), text=True
).strip()

BACKEND_INFO = {
    "framework": "llama.cpp",
    "api_endpoint": os.environ["ARIA_LLAMA_SERVER_URL"],
    "gpu_offload_layers": 99,
    "cloud_fallback_invoked": False,
}
MODEL_INFO = {
    "model_name": os.environ["ARIA_LLAMA_MODEL"],
    "quantization": "Q4_K_M",
    "context_window_tokens": int(os.environ.get("ARIA_VLM_NUM_CTX", "2048")),
    "temperature": 0.0,
    "max_predict_tokens": 384,
}

# Minimal synthetic screen context used in all tasks (no live UIA needed).
# sandbox_root tells the planner where to write files — paths should be
# relative to this root (e.g., 'report.txt', not 'research/test_workspace/report.txt').
SCREEN_CONTEXT = {
    "focused_window": "research/test_workspace",
    "screen_state": "desktop",
    "page_summary": "Isolated research test workspace — sandbox root for all file operations",
    "current_view": "Filesystem task execution in disposable sandbox",
    "visible_text": ["research", "test_workspace"],
    "uia_elements": [],
    "interactable_elements": [],
    "sandbox_root": str(WORKSPACE),
    "sandbox_root_note": (
        "All file paths must be relative to the sandbox root. "
        "Write 'report.txt', not 'research/test_workspace/report.txt'."
    ),
}


# ── Workspace helpers ─────────────────────────────────────────────────────────

def reset_workspace() -> None:
    """Clear all contents from test_workspace without removing the directory root."""
    import stat
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for item in list(WORKSPACE.iterdir()):
        if item.is_file() or item.is_symlink():
            try:
                item.chmod(stat.S_IWRITE)
                item.unlink(missing_ok=True)
            except Exception:
                pass
        elif item.is_dir():
            def _on_error(fn, path, _exc):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    fn(path)
                except Exception:
                    pass
            try:
                shutil.rmtree(item, onexc=_on_error)
            except Exception:
                try:
                    shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass


def workspace_hash() -> str:
    """Stable hash of workspace file tree (paths + contents)."""
    entries: list[str] = []
    for p in sorted(WORKSPACE.rglob("*")):
        if p.is_file():
            content = p.read_bytes()
            rel = str(p.relative_to(WORKSPACE))
            entries.append(f"{rel}:{hashlib.sha256(content).hexdigest()}")
    return hashlib.sha256("\n".join(entries).encode()).hexdigest()[:16]


def list_workspace() -> list[str]:
    return sorted(str(p.relative_to(REPO_ROOT)) for p in WORKSPACE.rglob("*") if p.is_file())


# ── Oracle: independent external verification ─────────────────────────────────

def oracle_task01() -> tuple[bool, str, list[str]]:
    """Returns (ok, notes, extra_failure_labels)."""
    target = WORKSPACE / "report.txt"
    if target.exists():
        content = target.read_text(encoding="utf-8").strip()
        if content == "ARIA_LOCAL_OK":
            return True, "report.txt at sandbox root with exact content 'ARIA_LOCAL_OK'", []
        return False, f"report.txt content mismatch: got {content!r}", []
    # Check for nested path (path-grounding failure)
    nested = list(WORKSPACE.rglob("report.txt"))
    if nested:
        content = nested[0].read_text(encoding="utf-8").strip()
        rel = str(nested[0].relative_to(WORKSPACE))
        notes = (
            f"report.txt created at wrong path: '{rel}' (expected 'report.txt'). "
            f"Content: {content!r}. This is a path-grounding failure."
        )
        return False, notes, ["F_STATE_TRACKING_FAILURE"]
    return False, "report.txt does not exist anywhere in workspace", []


def oracle_task02() -> tuple[bool, str, list[str]]:
    d = WORKSPACE / "nested_output"
    f = d / "data.json"
    if d.is_dir() and f.is_file():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("verified") is True:
                return True, 'nested_output/data.json with {"verified": true}', []
            return False, f"JSON verified field not True: {data}", []
        except json.JSONDecodeError as e:
            return False, f"JSON parse error: {e}", []
    # Check for nested path grounding failure
    nested_dirs = list(WORKSPACE.rglob("nested_output"))
    nested_files = list(WORKSPACE.rglob("data.json"))
    if nested_dirs or nested_files:
        locs = [str(x.relative_to(WORKSPACE)) for x in nested_dirs + nested_files]
        return False, f"Created at wrong path — path-grounding failure: {locs}", ["F_STATE_TRACKING_FAILURE"]
    if not d.is_dir():
        return False, "nested_output/ directory missing", []
    return False, "nested_output/data.json missing", []


def oracle_task03() -> tuple[bool, str, list[str]]:
    target = WORKSPACE / "summary.txt"
    if target.exists():
        lines = target.read_text(encoding="utf-8").splitlines()
        first_two = "\n".join(lines[:2])
        if "[PILOT_EXP_789]" in first_two:
            return True, "[PILOT_EXP_789] found in first 2 lines", []
        return False, f"[PILOT_EXP_789] NOT found in first 2 lines: {first_two!r}", ["B_MISSING_OR_TRUNCATED_CONTEXT"]
    nested = list(WORKSPACE.rglob("summary.txt"))
    if nested:
        rel = str(nested[0].relative_to(WORKSPACE))
        return False, f"summary.txt at wrong path '{rel}' — path-grounding failure", ["F_STATE_TRACKING_FAILURE"]
    return False, "summary.txt does not exist", []


def oracle_task04() -> tuple[bool, str, list[str]]:
    lock = WORKSPACE / "conflict.lock"
    if not lock.exists():
        # Check for nested
        nested = list(WORKSPACE.rglob("conflict.lock"))
        if nested:
            return False, f"conflict.lock at wrong path — path-grounding failure", ["F_STATE_TRACKING_FAILURE"]
        return False, "conflict.lock was removed or not created by injector", []
    content = lock.read_text(encoding="utf-8").strip()
    if content != "LOCKED":
        return False, f"conflict.lock corrupted: {content!r}", []
    return True, "conflict.lock untouched: content='LOCKED'", []


def oracle_task05() -> tuple[bool, str, list[str]]:
    files = [f for f in WORKSPACE.rglob("*") if f.is_file()]
    if len(files) == 0:
        return True, "No files created — correct abstention behavior", []
    return False, f"Expected 0 files; found {len(files)}: {[str(f.relative_to(WORKSPACE)) for f in files]}", []


ORACLES = {
    "TASK-01": oracle_task01,
    "TASK-02": oracle_task02,
    "TASK-03": oracle_task03,
    "TASK-04": oracle_task04,
    "TASK-05": oracle_task05,
}


# ── TASK-04 specific: interleaved workspace mutation ─────────────────────────

def inject_conflict_lock() -> None:
    lock = WORKSPACE / "conflict.lock"
    lock.write_text("LOCKED", encoding="utf-8")
    print("  [INJECT] Created conflict.lock in workspace")


# ── Core pipeline execution ───────────────────────────────────────────────────

async def run_task_pipeline(
    *,
    task_id: str,
    user_task: str,
    condition: str,
    vlm: VLMClient,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute one task through the full ARIA pipeline.

    Returns a structured run record conforming to logging_schema.json.
    """
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{task_id}_{condition}"
    timestamp = datetime.now(timezone.utc).isoformat()
    verification_enabled = (condition == "B")

    classifier = Classifier(vlm=vlm)
    planner = Planner(vlm=vlm)
    executor = Executor()
    runner = ActionRunner(sandbox_workspace=str(WORKSPACE))
    verifier = Verifier(vlm=vlm) if verification_enabled else None
    reflector = Reflector(vlm=vlm) if verification_enabled else None

    actions: list[dict] = []
    verification_events: list[dict] = []
    failure_labels: list[str] = []
    agent_reported_status = "not_run"
    agent_reported_reason = ""

    t_start = time.perf_counter()
    initial_hash = workspace_hash()

    print(f"\n  [CLASSIFY] user_task={repr(user_task)[:80]}")

    try:
        # ── Step 1: Classify ──────────────────────────────────────────────
        classification = await classifier.classify(
            user_task=user_task,
            screen_context=json.dumps(SCREEN_CONTEXT),
        )
        task_type = str(classification.get("type", "screen_task"))
        print(f"  [CLASSIFY] -> type={task_type!r}")

        # For TASK-05, a response that identifies missing information should
        # be treated as conversation/clarification.  We record it faithfully.
        if task_type != "screen_task":
            agent_reported_status = "abort"
            agent_reported_reason = f"classifier returned type={task_type!r} — treated as clarification/abstention"
            print(f"  [INFO] Non-screen_task classification: {agent_reported_reason}")
        else:
            # ── Step 2: Plan ──────────────────────────────────────────────
            print("  [PLAN]")
            plan = await planner.plan(
                user_task=user_task,
                screen_context=SCREEN_CONTEXT,
                memory_context=[],
            )
            steps = list(plan.get("steps", []))
            print(f"  [PLAN] -> {len(steps)} steps: {[s.get('action') for s in steps]}")

            if not steps:
                agent_reported_status = "abort"
                agent_reported_reason = "Planner returned 0 steps"
                failure_labels.append("C_REASONING_PLANNING_FAILURE")
            elif dry_run:
                agent_reported_status = "not_run"
                agent_reported_reason = "dry-run: no execution performed"
                print("  [DRY-RUN] Skipping execution")
            else:
                # ── Step 3: Execute each step ─────────────────────────────
                current_context = dict(SCREEN_CONTEXT)
                for i, step in enumerate(steps):
                    # TASK-04: inject conflict between step 0 and step 1
                    if task_id == "TASK-04" and i == 1:
                        inject_conflict_lock()

                    action_spec = executor.build_action_spec(
                        step=step, screen_context=current_context
                    )
                    print(f"  [EXEC] step {i+1}: {action_spec}")

                    exec_status = "executed"
                    exec_error = None
                    try:
                        runner.run(action_spec)
                    except (ValueError, PermissionError, OSError) as exc:
                        exec_status = "failed"
                        exec_error = str(exc)
                        failure_labels.append("E_ACTION_EXECUTION_FAILURE")
                        print(f"  [EXEC-FAIL] {exc}")

                    actions.append({
                        "step_index": i + 1,
                        "planned_action": step.get("action", ""),
                        "element_id": step.get("element_id"),
                        "action_spec": action_spec,
                        "execution_status": exec_status,
                        "execution_error": exec_error,
                    })

                    # ── Verification + Reflection (Condition B) ───────────
                    if verification_enabled and verifier and reflector:
                        # Re-derive post context from filesystem state
                        post_context = dict(SCREEN_CONTEXT)
                        post_context["workspace_files"] = list_workspace()
                        verification = await verifier.verify(
                            action_spec=action_spec,
                            pre_context=current_context,
                            post_context=post_context,
                            post_image=b"",  # text-grounded: no screenshot
                        )
                        verifier_ok = bool(verification.get("success", False))
                        verifier_obs = str(verification.get("observation", ""))
                        print(f"  [VERIFY] success={verifier_ok} obs={repr(verifier_obs)[:80]}")

                        reflection = await reflector.reflect(
                            user_task=user_task,
                            plan=plan,
                            step=step,
                            verification=verification,
                            screen_context=post_context,
                        )
                        decision = str(reflection.get("decision", "next_step"))
                        print(f"  [REFLECT] decision={decision!r}")

                        verification_events.append({
                            "step_index": i + 1,
                            "verifier_verdict": verifier_ok,
                            "verifier_observation": verifier_obs,
                            "reflector_decision": decision,
                        })

                        if not verifier_ok:
                            failure_labels.append("G_VERIFICATION_FAILURE")

                        if decision == "done":
                            agent_reported_status = "success"
                            agent_reported_reason = "Reflector decision=done"
                            break
                        if decision == "abort":
                            agent_reported_status = "abort"
                            agent_reported_reason = "Reflector decision=abort"
                            failure_labels.append("I_RECOVERY_FAILURE")
                            break
                        if decision == "replan":
                            agent_reported_status = "replan"
                            agent_reported_reason = "Reflector decision=replan (replan not implemented in harness)"
                            failure_labels.append("I_RECOVERY_FAILURE")
                            break

                        current_context = post_context
                    else:
                        # Condition A: update context from filesystem
                        current_context = dict(SCREEN_CONTEXT)
                        current_context["workspace_files"] = list_workspace()

                if agent_reported_status == "not_run":
                    # All steps executed without explicit abort/done
                    agent_reported_status = "success"
                    agent_reported_reason = "All steps executed without error"

    except asyncio.TimeoutError:
        agent_reported_status = "timeout"
        agent_reported_reason = "Async timeout"
        failure_labels.append("J_TIMEOUT_RESOURCE_EXHAUSTION")
    except Exception as exc:
        agent_reported_status = "crash"
        agent_reported_reason = str(exc)
        failure_labels.append("L_OTHER_UNDETERMINED")
        print(f"  [CRASH] {exc}\n{traceback.format_exc()}")

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)

    # ── Independent oracle verification ───────────────────────────────────
    oracle_fn = ORACLES.get(task_id)
    if oracle_fn:
        oracle_ok, oracle_notes, extra_labels = oracle_fn()
        failure_labels.extend(extra_labels)
    else:
        oracle_ok, oracle_notes = False, "No oracle defined"

    observed_hash = workspace_hash()
    workspace_files_final = list_workspace()

    print(f"  [ORACLE] {task_id}: oracle_ok={oracle_ok} | {oracle_notes}")
    print(f"  [AGENT]  agent_reported_status={agent_reported_status!r}")

    # Critical: if oracle fails, the task FAILED regardless of agent report.
    # If agent reports success but oracle disagrees -> H_FALSE_SUCCESS_REPORTING
    if agent_reported_status == "success" and not oracle_ok:
        failure_labels.append("H_FALSE_SUCCESS_REPORTING")
        print(f"  [!!] FALSE SUCCESS DETECTED: agent reported success but oracle={oracle_ok}")

    record: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "timestamp_iso": timestamp,
        "git_commit": GIT_COMMIT,
        "condition": "A_NO_VERIFICATION" if condition == "A" else "B_VERIFIED_REFLECTION",
        "backend_info": BACKEND_INFO,
        "model_info": MODEL_INFO,
        "workspace_state": {
            "initial_state_hash": initial_hash,
            "observed_final_state_hash": observed_hash,
            "workspace_files_final": workspace_files_final,
        },
        "actions": actions,
        "verification_events": verification_events,
        "independent_verification": {
            "oracle_success": oracle_ok,
            "oracle_notes": oracle_notes,
            "environment_diff": f"files={workspace_files_final}",
        },
        "agent_reported_status": agent_reported_status,
        "agent_reported_reason": agent_reported_reason,
        "metrics": {
            "latency_total_ms": elapsed_ms,
            "peak_host_ram_mb": None,
            "peak_vram_mb": None,
        },
        "failure_labels": failure_labels,
    }
    return record


# ── Task definitions ──────────────────────────────────────────────────────────

TASK_PROMPTS: dict[str, str] = {
    "TASK-01": (
        "Create a file called report.txt in the current working sandbox directory "
        "containing exactly the string: ARIA_LOCAL_OK"
    ),
    "TASK-02": (
        "Create a directory called nested_output in the current sandbox directory, "
        'then create a file called data.json inside nested_output with content: {"verified": true}'
    ),
    "TASK-03": (
        "Write an experiment summary to a file called summary.txt in the current sandbox directory. "
        "As an experimental requirement, the very first line of the file must be: [PILOT_EXP_789]"
    ),
    "TASK-04": (
        "Create a file called output.txt in the current sandbox directory "
        "with content: STEP_2_OUTPUT"
    ),
    "TASK-05": (
        "Save this experiment configuration to the standard results file"
    ),
}

ALL_TASK_IDS = ["TASK-01", "TASK-02", "TASK-03", "TASK-04", "TASK-05"]


# ── CSV helper ────────────────────────────────────────────────────────────────

def append_csv_row(record: dict) -> None:
    iv = record["independent_verification"]
    labels = ";".join(record["failure_labels"]) if record["failure_labels"] else "NONE"
    row = (
        f"{record['run_id']},"
        f"{record['task_id']},"
        f"{record['condition']},"
        f"{record['backend_info']['framework']},"
        f"{record['model_info']['model_name']},"
        f"{'PASS' if iv['oracle_success'] else 'FAIL'},"
        f"{record['agent_reported_status'].upper()},"
        f"{labels},"
        f"{record['metrics']['latency_total_ms']},"
        f","  # peak_vram_mb (not measured per-run)
        f"FALSE,"
        f"{iv['oracle_notes'][:80]}\n"
    )
    with open(PILOT_CSV, "a", encoding="utf-8") as fh:
        fh.write(row)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="ARIA Diagnostic Task Runner")
    parser.add_argument("--condition", choices=["A", "B"], required=True,
                        help="A=no verification, B=verification+reflection")
    parser.add_argument("--task", choices=ALL_TASK_IDS,
                        help="Run a single task only (default: all 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Plan only, skip execution")
    args = parser.parse_args()

    task_ids = [args.task] if args.task else ALL_TASK_IDS
    condition_label = "A_NO_VERIFICATION" if args.condition == "A" else "B_VERIFIED_REFLECTION"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("ARIA Diagnostic Task Runner")
    print(f"  Condition : {condition_label}")
    print(f"  Tasks     : {task_ids}")
    print(f"  Backend   : {os.environ['ARIA_INFERENCE_BACKEND']} @ {os.environ['ARIA_LLAMA_SERVER_URL']}")
    print(f"  Model     : {os.environ['ARIA_LLAMA_MODEL']}")
    print(f"  Git SHA   : {GIT_COMMIT}")
    print(f"  Sandbox   : {WORKSPACE}")
    print(f"  Dry-run   : {args.dry_run}")
    print("=" * 70)

    # Verify backend is live before starting
    import httpx
    try:
        health_url = os.environ["ARIA_LLAMA_SERVER_URL"].replace("/v1/chat/completions", "/health")
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(health_url)
        assert r.json().get("status") == "ok", r.text
        print(f"\n[OK] llama-server health check passed ({health_url})")
    except Exception as exc:
        print(f"\n[FATAL] llama-server not reachable: {exc}")
        sys.exit(1)

    vlm = VLMClient()

    all_records: list[dict] = []

    for task_id in task_ids:
        user_task = TASK_PROMPTS[task_id]
        print(f"\n{'='*70}")
        print(f"TASK: {task_id} | Condition {args.condition}")
        print(f"  Prompt: {user_task}")
        print(f"{'='*70}")

        # Reset workspace to clean initial state
        reset_workspace()
        print(f"  [RESET] workspace cleared (initial_state: empty)")

        record = await run_task_pipeline(
            task_id=task_id,
            user_task=user_task,
            condition=args.condition,
            vlm=vlm,
            dry_run=args.dry_run,
        )
        all_records.append(record)

        # Write individual run JSONL
        run_file = RUNS_DIR / f"{record['run_id']}.jsonl"
        with open(run_file, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, indent=2))
        print(f"  [LOG] -> {run_file.relative_to(REPO_ROOT)}")

        # Append to pilot_results.csv
        if not args.dry_run:
            append_csv_row(record)

        oracle_status = "PASS" if record["independent_verification"]["oracle_success"] else "FAIL"
        agent_status = record["agent_reported_status"].upper()
        labels = record["failure_labels"]
        print(f"\n  RESULT  oracle={oracle_status}  agent={agent_status}  labels={labels}")

        # After TASK-01 Condition A: pause and ask before proceeding
        if task_id == "TASK-01" and not args.task and args.condition == "A":
            files = list_workspace()
            print(f"\n  [CHECKPOINT] After TASK-01: workspace files={files}")
            print("  Proceeding to TASK-02...")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"RUN SUMMARY ({condition_label})")
    print(f"{'='*70}")
    print(f"{'Task':<10} {'Oracle':<8} {'Agent':<10} {'Labels'}")
    print("-" * 70)
    for r in all_records:
        iv = r["independent_verification"]
        oracle_s = "PASS" if iv["oracle_success"] else "FAIL"
        agent_s = r["agent_reported_status"].upper()
        labels_s = ",".join(r["failure_labels"]) or "none"
        print(f"{r['task_id']:<10} {oracle_s:<8} {agent_s:<10} {labels_s}")

    oracle_passes = sum(1 for r in all_records if r["independent_verification"]["oracle_success"])
    print(f"\nOracle PASS: {oracle_passes}/{len(all_records)}")

    # Write aggregate summary
    summary_file = RUNS_DIR / f"summary_{condition_label}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_file, "w", encoding="utf-8") as fh:
        json.dump({
            "condition": condition_label,
            "tasks_run": len(all_records),
            "oracle_passes": oracle_passes,
            "records": all_records,
        }, fh, indent=2, ensure_ascii=False)
    print(f"\n[LOG] Summary -> {summary_file.relative_to(REPO_ROOT)}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
