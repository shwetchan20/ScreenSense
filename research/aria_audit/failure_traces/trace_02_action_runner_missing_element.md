# Failure Trace 02: Unvalidated Element ID & Executor StopIteration / KeyError Crash

## 1. Initial Conditions
* **Module**: `src/aria/agent/executor.py` and `src/aria/agent/action_runner.py`.
* **Caller**: `AriaRuntime._run_screen_task()` in `src/aria/main.py`.
* **State**: Screen context gathered with a list of `interactable_elements` (max 16 elements parsed from UIA).

## 2. Relevant Observation & Context
The Planner (`Planner.plan`) prompts the model to generate a plan:
```json
{
  "steps": [
    {"step": 1, "action": "click", "element_id": 99}
  ]
}
```
In real desktop environments, small language models frequently hallucinate element IDs, output 1-based indices exceeding the list length, or reference element IDs that disappeared between frames.

## 3. Code Under Execution
In `src/aria/agent/executor.py`:
```python
class Executor:
    def build_action_spec(self, *, step: dict, screen_context: dict) -> dict:
        action = str(step["action"])
        spec: dict[str, object] = {"action": action}

        if "element_id" in step:
            element_id = int(step["element_id"])
            elements = screen_context["interactable_elements"]
            element = next(e for e in elements if int(e["id"]) == element_id)
            center = element["center"]
            spec["coords"] = {"x": int(center[0]), "y": int(center[1])}
        ...
        return spec
```

And in `src/aria/agent/action_runner.py`:
```python
class ActionRunner:
    def run(self, action_spec: dict) -> None:
        action = str(action_spec["action"])
        if action == "click":
            coords = action_spec["coords"]
            pyautogui.click(int(coords["x"]), int(coords["y"]))
```

## 4. Model Output (Simulated or Real Planner Output)
```json
{"steps": [{"step": 1, "action": "click", "element_id": 99}]}
```

## 5. Actual Outcome & Empirical Reproduction
Command executed:
```powershell
.\.venv\Scripts\python.exe -c "from aria.agent.executor import Executor; e = Executor(); e.build_action_spec(step={'action': 'click', 'element_id': 99}, screen_context={'interactable_elements': []})"
```

Observed Traceback:
```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    from aria.agent.executor import Executor; e = Executor(); e.build_action_spec(step={'action': 'click', 'element_id': 99}, screen_context={'interactable_elements': []})
  File "C:\Users\shwet k\OneDrive\Desktop\screensense\src\aria\agent\executor.py", line 12, in build_action_spec
    element = next(e for e in elements if int(e["id"]) == element_id)
StopIteration
```

* **Case A (`element_id` not found in `elements`)**:
  `next(e for e in elements if int(e["id"]) == element_id)` fails with `StopIteration`. Because this exception is unhandled in `main.py`, the entire agent pipeline crashes immediately without recording a reflection or attempting recovery.
* **Case B (`action == "click"` but model provides coordinates or omits `element_id`)**:
  `spec` does not have `"coords"`. When passed to `ActionRunner.run`, `action_spec["coords"]` raises `KeyError: 'coords'`, crashing the process.
* **Case C (Unrestricted click)**:
  If coordinates are computed, `pyautogui.click` immediately clicks the physical desktop screen, potentially focusing or clicking outside test boundaries.

## 6. Agent-Reported Outcome
Crash with uncaught exception (`StopIteration` or `KeyError`).

## 7. Independent Verifier Result
`FAIL` (Action aborted due to internal exception; no verifier / reflection executed).

## 8. Failure Classification
* **Primary Label**: `D_INVALID_UNSUPPORTED_ACTION`
* **Secondary Label**: `C_REASONING_PLANNING_FAILURE`
* **Tertiary Label**: `E_ACTION_EXECUTION_FAILURE`

## 9. Why This Trace Matters
This trace exposes that ARIA has no defensive validation layer between the model's output and the operating system. When evaluating local small models (such as 7B models), invalid action formatting and hallucinated element IDs are frequent. Without schema validation and graceful error feedback to the planner/reflector, task completion drops to zero on the first malformed step.
