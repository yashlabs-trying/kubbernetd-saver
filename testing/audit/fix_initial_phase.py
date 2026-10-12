filepath = "/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/kubbernetd/operator/rg_controller.py"
with open(filepath, "r") as f:
    content = f.read()

old = """    def _initial_phase(self, spec: dict) -> GroupPhase:
        target = spec.get("targetRef", {})
        name = target.get("name", "")
        if not name:
            return GroupPhase.UNKNOWN
        return GroupPhase.RUNNING"""

new = """    def _initial_phase(self, spec: dict) -> GroupPhase:
        target = spec.get("targetRef", {})
        name = target.get("name", "")
        if not name:
            return GroupPhase.UNKNOWN
        spec_model = spec.get("model", {})
        workers = spec_model.get("workers", 1)
        if workers == 0:
            return GroupPhase.SLEEPING
        return GroupPhase.RUNNING"""

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("FIXED")
else:
    print("PATTERN_NOT_FOUND")
