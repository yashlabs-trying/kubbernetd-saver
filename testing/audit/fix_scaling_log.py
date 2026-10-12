filepath = "/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/kubbernetd/operator/rg_controller.py"
with open(filepath, "r") as f:
    content = f.read()

old = """    def _handle_scaling_down(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        try:
            target = state.spec.get("targetRef", {}).get("name", "")
            kind = state.spec.get("targetRef", {}).get("kind", "Deployment")
            if kind == "Deployment" and target:
                self.apps_api.patch_namespaced_deployment_scale(
                    name=target, namespace=namespace, body={"spec": {"replicas": 0}},
                )
            state.current_workers = 0"""

new = """    def _handle_scaling_down(self, name: str, namespace: str, state: ReplicaGroupState, now: float):
        try:
            target = state.spec.get("targetRef", {}).get("name", "")
            kind = state.spec.get("targetRef", {}).get("kind", "Deployment")
            log.info("executing scale-down", target=target, kind=kind, rg_name=name)
            if kind == "Deployment" and target:
                self.apps_api.patch_namespaced_deployment_scale(
                    name=target, namespace=namespace, body={"spec": {"replicas": 0}},
                )
                log.info("scale-down API call completed", target=target)
            state.current_workers = 0"""

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("FIXED")
else:
    print("PATTERN_NOT_FOUND")
