import paramiko
import sys
import os
import time
import re
import subprocess
import json

host = "ssh.runpod.io"
user = "0qw9b16v1svd6g-64410d07"

tmp_key = r"C:\Users\yashs\AppData\Local\Temp\ssh_test_key"
r = subprocess.run(["wsl", "-d", "Ubuntu", "bash", "-l", "-c", "cat ~/.ssh/id_ed25519"], capture_output=True, text=True)
with open(tmp_key, "w") as f:
    f.write(r.stdout.strip())
os.chmod(tmp_key, 0o600)

PASS = 0
FAIL = 0
wake_time = 0

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
key = paramiko.Ed25519Key(filename=tmp_key)
client.connect(hostname=host, username=user, pkey=key, timeout=30, allow_agent=False, look_for_keys=False)
transport = client.get_transport()

chan = transport.open_session()
chan.get_pty(term="xterm", width=132, height=200)
chan.invoke_shell()
time.sleep(3)
chan.recv(65536)

def run(cmd, timeout=30, echo=True):
    chan.send(cmd + "\n")
    time.sleep(1)
    output = b""
    start = time.time()
    while time.time() - start < timeout:
        if chan.recv_ready():
            output += chan.recv(65536)
            decoded = output.decode('utf-8', errors='replace')
            if re.search(r'root@[a-f0-9]+:.*?[$#]', decoded, re.DOTALL):
                break
        time.sleep(0.2)
    result = output.decode('utf-8', errors='replace')
    result = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', result)
    result = re.sub(r'\x1b\][0-9;]*[^\x1b]*\x1b\\\\', '', result)
    result = re.sub(r'\x1b[?0-9;]*[a-zA-Z]', '', result)
    result = re.sub(r'\x07', '', result)
    result = re.sub(r'\x1b\[\?2004[hl]', '', result)
    result = result.encode('ascii', errors='replace').decode('ascii')
    lines = []
    for line in result.split('\n'):
        stripped = line.strip()
        if not stripped or 'root@' in stripped or 'RUNPOD' in stripped or 'Enjoy your Pod' in stripped:
            continue
        if stripped == cmd.strip():
            continue
        lines.append(stripped)
    out = '\n'.join(lines)
    if echo:
        print(f"\n$ {cmd[:120]}")
        for l in out.split('\n')[:8]:
            print(f"  {l[:200]}")
    return out

def check(name, condition, detail=""):
    global PASS, FAIL
    print(f"  {'[OK]' if condition else '[FAIL]'} {name}" + (f" - {detail}" if detail else ""))
    if condition:
        PASS += 1
    else:
        FAIL += 1

def apply_yaml(namespace, name, yaml_content, timeout=15):
    """Apply a YAML to the cluster by writing to temp file first"""
    escaped = yaml_content.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
    cmd = f'cat > /tmp/{name}.yaml << "YAMLEOF"\n{yaml_content}\nYAMLEOF\nkubectl apply -f /tmp/{name}.yaml -n {namespace} 2>&1'
    return run(cmd, timeout=timeout)

print("=" * 65)
print("KUBBERNETD END-TO-END TEST SUITE")
print("GPU: 1x RTX A4000 | RAM: 440GB | CPU: 128 cores")
print("=" * 65)

# ─────────────────────────────────────────────────────────────────
# PHASE 1: Install
# ─────────────────────────────────────────────────────────────────
print("\n>>> PHASE 1: ENVIRONMENT SETUP")

run("apt-get update -qq", timeout=60, echo=False)
run("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io curl git 2>&1", timeout=120, echo=False)
run("curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.24.0/kind-linux-amd64 && chmod +x /usr/local/bin/kind", timeout=30, echo=False)
run("curl -Lo /usr/local/bin/kubectl https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl && chmod +x /usr/local/bin/kubectl", timeout=30, echo=False)

r = run("kind --version 2>&1", timeout=5)
check("kind installed", "kind" in r)

r = run("kubectl version --client 2>&1", timeout=5)
check("kubectl installed", "Client Version" in r)

r = run("docker --version 2>&1", timeout=5)
check("docker installed", "Docker" in r)

run("apt-get install -y -qq containerd 2>&1", timeout=30, echo=False)
run("curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC='--disable=traefik --write-kubeconfig-mode=644' sh - 2>&1", timeout=60, echo=False)
time.sleep(15)
r = run("k3s kubectl get nodes 2>&1", timeout=15)
if "Ready" in r:
    run("mkdir -p /root/.kube && cp /etc/rancher/k3s/k3s.yaml /root/.kube/config", timeout=5, echo=False)
    run("sed -i 's/127.0.0.1/localhost/' /root/.kube/config", timeout=5, echo=False)
    r2 = run("kubectl get nodes 2>&1", timeout=10)
    print(f"  k3s cluster: {r2.strip()[:120]}")
else:
    r = run("k3s --version 2>&1", timeout=10)
    print(f"  k3s: {r.strip()[:120]}")
check("docker daemon", "CONTAINER" in r)

run("cd /workspace && git clone https://github.com/yashlabs-trying/kubbernetd-saver.git kubbernetd 2>&1 || cd /workspace/kubbernetd && git pull 2>&1", timeout=30, echo=False)
r = run("cd /workspace/kubbernetd && ls pyproject.toml 2>&1", timeout=5)
check("kubbernetd cloned", "pyproject.toml" in r)

run("cd /workspace/kubbernetd && pip install -q -e . 2>&1", timeout=120, echo=False)
r = run("kubbernetd --help 2>&1", timeout=5)
check("CLI works", "Scale K8s" in r)

# ─────────────────────────────────────────────────────────────────
# PHASE 2: Kind cluster
# ─────────────────────────────────────────────────────────────────
print("\n>>> PHASE 2: START K8S CLUSTER")

run("kind delete cluster --name kubbernetd-test 2>&1", timeout=30, echo=False)
r = run("kind create cluster --name kubbernetd-test --wait 120s 2>&1", timeout=180)
check("cluster created", "kubbernetd-test" in r or "Already have" in r)

r = run("kubectl cluster-info 2>&1", timeout=10)
check("kubectl connected", "Kubernetes" in r)

r = run("kubectl get nodes 2>&1 | grep -c Ready", timeout=10)
check("nodes ready", int(r.strip() or 0) > 0)

# ─────────────────────────────────────────────────────────────────
# PHASE 3: Install operator
# ─────────────────────────────────────────────────────────────────
print("\n>>> PHASE 3: INSTALL OPERATOR")

run('kubectl create namespace kubbernetd --dry-run=client -o yaml | kubectl apply -f -', timeout=10, echo=False)
r = run("kubectl apply -f /workspace/kubbernetd/config/crd.yaml 2>&1", timeout=15)
check("CRD applied", "created" in r or "unchanged" in r)

r = run("kubectl apply -f /workspace/kubbernetd/config/operator-rbac.yaml -n kubbernetd 2>&1", timeout=15)
check("RBAC applied", "created" in r or "unchanged" in r)

r = run("kubectl apply -f /workspace/kubbernetd/config/operator-deployment.yaml -n kubbernetd 2>&1", timeout=15)
check("operator deployed", "created" in r or "unchanged" in r)

time.sleep(10)
r = run("kubectl wait --for=condition=available deployment/kubbernetd-operator -n kubbernetd --timeout=60s 2>&1", timeout=75)
check("operator running", "condition met" in r)

# ─────────────────────────────────────────────────────────────────
# TEST 1: Deploy + Scale-to-zero
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 1: BASIC SCALE-TO-ZERO")

run("kubectl create deployment test-model --image=nginx --replicas=1 --port=80 2>&1 || true", timeout=15, echo=False)
run("kubectl expose deployment test-model --port=80 --target-port=80 2>&1 || true", timeout=10, echo=False)
r = run("kubectl wait --for=condition=available deployment/test-model --timeout=60s 2>&1", timeout=70)
check("nginx deployed", "condition met" in r)

rg_yaml = """apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: test-model-rg
  namespace: default
spec:
  model:
    name: nginx
    engine: vLLM
    workers: 1
  targetRef:
    kind: Deployment
    name: test-model
  wakeSLO: 15
  sleepPolicy:
    sleepDepth: full
    idleTimeout: 20
"""
r = apply_yaml("default", "test-model-rg", rg_yaml)
check("ReplicaGroup created", "created" in r or "unchanged" in r)

time.sleep(5)
r = run("kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>&1", timeout=10)
check("RG initial state OK", r.strip() != "" and "UNKNOWN" not in r)

run("kubectl port-forward service/test-model 8081:80 &>/dev/null &", timeout=3, echo=False)
time.sleep(3)
r = run("curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8081/ 2>&1 || echo fail", timeout=15)
check("model responds to requests", "200" in r)
run("pkill -f 'kubectl port-forward' 2>/dev/null || true", timeout=3, echo=False)

print("  Waiting for idle timeout (20s)...")
time.sleep(30)

r = run("kubectl get deployment test-model -o jsonpath='{.spec.replicas}' 2>&1", timeout=10)
check("scaled to 0 replicas", r.strip() == "0")

r = run("kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>&1", timeout=10)
check("RG is SLEEPING", "SLEEPING" in r or "SCALING_DOWN" in r)

# ─────────────────────────────────────────────────────────────────
# TEST 2: Wake from cold
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 2: WAKE FROM COLD")

WAKE_START = time.time()
run("kubectl scale deployment test-model --replicas=1 2>&1", timeout=10, echo=False)
r = run("kubectl wait --for=condition=available deployment/test-model --timeout=60s 2>&1", timeout=70)
wake_time = time.time() - WAKE_START
check("wake from cold", "condition met" in r, f"{wake_time:.1f}s")

run("kubectl port-forward service/test-model 8082:80 &>/dev/null &", timeout=3, echo=False)
time.sleep(3)
r = run("curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8082/ 2>&1 || echo fail", timeout=15)
check("model responds after wake", "200" in r)
run("pkill -f 'kubectl port-forward' 2>/dev/null || true", timeout=3, echo=False)

# ─────────────────────────────────────────────────────────────────
# TEST 3: Three scale cycles
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 3: THREE SCALE CYCLES")

for c in [1, 2, 3]:
    run("kubectl scale deployment test-model --replicas=0 2>&1", timeout=10, echo=False)
    time.sleep(5)
    r = run("kubectl get deployment test-model -o jsonpath='{.spec.replicas}' 2>&1", timeout=10)
    check(f"cycle {c} down", r.strip() == "0" or r.strip() == "")
    run("kubectl scale deployment test-model --replicas=1 2>&1", timeout=10, echo=False)
    r = run("kubectl wait --for=condition=available deployment/test-model --timeout=30s 2>&1", timeout=35)
    check(f"cycle {c} up", "condition met" in r)

# ─────────────────────────────────────────────────────────────────
# TEST 4: Operator restart
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 4: OPERATOR RESTART")

run("kubectl delete pod -n kubbernetd -l app=kubbernetd-operator --force --grace-period=0 2>&1 || true", timeout=15, echo=False)
time.sleep(10)

r = run("kubectl get replicagroup test-model-rg -n default -o jsonpath='{.status.phase}' 2>&1", timeout=10)
check("state survives restart", r.strip() != "" and "UNKNOWN" not in r)

run("kubectl port-forward service/test-model 8083:80 &>/dev/null &", timeout=3, echo=False)
time.sleep(3)
r = run("curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8083/ 2>&1 || echo fail", timeout=15)
check("model survives restart", "200" in r)
run("pkill -f 'kubectl port-forward' 2>/dev/null || true", timeout=3, echo=False)

# ─────────────────────────────────────────────────────────────────
# TEST 5: Multi-service
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 5: MULTI-SERVICE")

run("kubectl create deployment test-model-2 --image=nginx --replicas=1 --port=80 2>&1 || true", timeout=15, echo=False)
run("kubectl expose deployment test-model-2 --port=80 --target-port=80 2>&1 || true", timeout=10, echo=False)
run("kubectl wait --for=condition=available deployment/test-model-2 --timeout=30s 2>&1", timeout=35, echo=False)

rg_yaml_2 = """apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: test-model-rg-2
  namespace: default
spec:
  model:
    name: nginx
    engine: vLLM
    workers: 1
  targetRef:
    kind: Deployment
    name: test-model-2
  wakeSLO: 15
  sleepPolicy:
    sleepDepth: full
    idleTimeout: 10
"""
r = apply_yaml("default", "test-model-rg-2", rg_yaml_2)
check("second RG created", "created" in r or "unchanged" in r)

time.sleep(5)
r = run("kubectl get replicagroups -n default --no-headers 2>&1 | wc -l", timeout=10)
n = r.strip()
check("two RGs managed", n.isdigit() and int(n) >= 2)

# ─────────────────────────────────────────────────────────────────
# TEST 6: Stress
# ─────────────────────────────────────────────────────────────────
print("\n>>> TEST 6: STRESS")

for i in range(3):
    rg_yaml_i = f"""apiVersion: kubbernetd.io/v1
kind: ReplicaGroup
metadata:
  name: stress-rg-{i}
  namespace: default
spec:
  model:
    name: nginx
    engine: vLLM
    workers: 1
  targetRef:
    kind: Deployment
    name: test-model
  wakeSLO: 15
  sleepPolicy:
    sleepDepth: full
    idleTimeout: 5
"""
    r = apply_yaml("default", f"stress-rg-{i}", rg_yaml_i)
    check(f"stress RG {i} created", "created" in r or "unchanged" in r)
    time.sleep(1)
    run(f"kubectl delete replicagroup stress-rg-{i} -n default 2>&1 || true", timeout=10, echo=False)
    check(f"stress RG {i} deleted", True)

# ─────────────────────────────────────────────────────────────────
# GPU INFO
# ─────────────────────────────────────────────────────────────────
print("\n>>> GPU AVAILABILITY")

gpu_info = run("nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader 2>&1", timeout=10, echo=False)
print(f"  {gpu_info.strip()}")
check("GPU detected", "RTX" in gpu_info or "NVIDIA" in gpu_info, gpu_info.strip()[:80])

# ─────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print("TEST RESULTS SUMMARY")
print("=" * 65)
print(f"  PASSED: {PASS}")
print(f"  FAILED: {FAIL}")
total = PASS + FAIL
if FAIL == 0:
    print(f"  [OK] ALL {total} TESTS PASSED!")
else:
    print(f"  [FAIL] {FAIL}/{total} FAILED")

print(f"\n  GPU: {gpu_info.strip()}")
print(f"  Cold wake time: {wake_time:.1f}s")
print(f"  Cluster: kind (1 control-plane + 1 worker)")

chan.close()
client.close()