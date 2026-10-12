from __future__ import annotations


class Executor:
    def build_action_spec(self, *, step: dict, screen_context: dict) -> dict:
        action = str(step.get("action", ""))
        spec: dict[str, object] = {"action": action}

        if "element_id" in step:
            try:
                element_id = int(step["element_id"])
                elements = screen_context.get("interactable_elements", [])
                element = next((e for e in elements if int(e.get("id", -1)) == element_id), None)
                if element and "center" in element:
                    center = element["center"]
                    spec["coords"] = {"x": int(center[0]), "y": int(center[1])}
                else:
                    spec["element_id_missing"] = True
            except (ValueError, TypeError):
                spec["element_id_missing"] = True

        if "coords" in step and isinstance(step["coords"], dict):
            spec["coords"] = step["coords"]
        if "text" in step:
            spec["text"] = str(step["text"])
        if "key" in step:
            spec["key"] = step["key"]
        if "amount" in step:
            spec["amount"] = int(step["amount"])
        if "target" in step:
            spec["target"] = str(step["target"])
        if "path" in step:
            spec["path"] = str(step["path"])
        if "content" in step:
            spec["content"] = str(step["content"])

        return spec

