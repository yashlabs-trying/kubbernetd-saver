import re

filepath = "/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/kubbernetd/operator/rg_controller.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix 1: Allow RUNNING -> SLEEPING transition
content = content.replace(
    "GroupPhase.RUNNING: [GroupPhase.DRAINING, GroupPhase.ERROR],",
    "GroupPhase.RUNNING: [GroupPhase.DRAINING, GroupPhase.SLEEPING, GroupPhase.ERROR],"
)

# Fix 2: Make _handle_running check for wake annotation when workers == 0
old = """    def _handle_running(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        spec = state.spec
        sleep_policy = spec.get("sleepPolicy", {})
        idle_timeout = sleep_policy.get("idleTimeout", self.config.idle_timeout_seconds)
        if idle_timeout <= 0:
            return
        self._reconcile_worker_count(name, namespace, state)
        if state.current_workers == 0:
            self._transition(name, namespace, state, GroupPhase.SLEEPING)
            return"""

new = """    def _handle_running(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        spec = state.spec
        sleep_policy = spec.get("sleepPolicy", {})
        idle_timeout = sleep_policy.get("idleTimeout", self.config.idle_timeout_seconds)
        if idle_timeout <= 0:
            return
        self._reconcile_worker_count(name, namespace, state)
        if state.current_workers == 0:
            if self._wake_requested(name, namespace):
                log.info("wake requested while at 0 workers, transitioning to ALLOCATING",
                          name=name, namespace=namespace)
                state.wake_started_at = now
                state.status.wakeCount += 1
                self._clear_wake_annotation(name, namespace)
                self._transition(name, namespace, state, GroupPhase.ALLOCATING)
                return
            self._transition(name, namespace, state, GroupPhase.SLEEPING)
            return"""

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("FIXED")
else:
    print("PATTERN_NOT_FOUND")
    # Show the actual content around _handle_running
    idx = content.find("def _handle_running")
    if idx >= 0:
        print(content[idx:idx+800])
