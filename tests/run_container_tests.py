import paramiko, sys, os, time, re, subprocess

host = "ssh.runpod.io"
user = "0qw9b16v1svd6g-64410d07"

tmp_key = r"C:\Users\yashs\AppData\Local\Temp\ssh_test_key"
r = subprocess.run(["wsl", "-d", "Ubuntu", "bash", "-l", "-c", "cat ~/.ssh/id_ed25519"], capture_output=True, text=True)
with open(tmp_key, "w") as f:
    f.write(r.stdout.strip())
os.chmod(tmp_key, 0o600)

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

def send(cmd, timeout=30):
    chan.send(cmd + "\n")
    time.sleep(1)
    out = b""
    start = time.time()
    while time.time() - start < timeout:
        if chan.recv_ready():
            out += chan.recv(65536)
            decoded = out.decode("utf-8", errors="replace")
            if re.search(r'root@[a-f0-9]+:.*?[$#]', decoded, re.DOTALL):
                break
        time.sleep(0.2)
    result = out.decode("utf-8", errors="replace")
    for pat in [r"\x1b\[[0-9;]*[a-zA-Z]", r"\x1b\][0-9;]*[^\x1b]*\x1b\\\\", r"\x1b[?0-9;]*[a-zA-Z]", r"\x07", r"\x1b\[\?2004[hl]"]:
        result = re.sub(pat, "", result)
    result = result.encode("ascii", errors="replace").decode("ascii")
    lines = [l.strip() for l in result.split("\n") if l.strip() and "root@" not in l and "RUNPOD" not in l and "Enjoy" not in l and l.strip() != cmd.strip()]
    return "\n".join(lines)

def heading(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")

heading("1. INSTALL KUBBERNETD")
out = send("cd /workspace/kubbernetd && pip install -q -e . 2>&1", 120)
print(out[-400:] if len(out) > 400 else out)

heading("2. RUN PYTEST (full suite)")
out = send("cd /workspace/kubbernetd && python -m pytest tests/ -v --tb=line 2>&1", 180)
summary = [l for l in out.split("\n") if "passed" in l and "failed" in l]
failures = [l for l in out.split("\n") if "FAILED" in l]
print(f"  Total failures: {len(failures)}")
for f in failures[:5]:
    print(f"  {f[:150]}")
if summary:
    print(f"  {summary[0][:100]}")

heading("3. INDIVIDUAL TEST RUNS")
modules = [
    ("IdleDetector", "tests/test_monitor/test_idle_detector.py"),
    ("RG Controller", "tests/test_operator/test_rg_controller.py"),
    ("Proxy buffer", "tests/test_proxy/test_buffer.py"),
    ("Proxy discovery", "tests/test_proxy/test_discovery.py"),
    ("Proxy warmup", "tests/test_proxy/test_warmup.py"),
    ("Optimizer", "tests/test_operator/test_optimizer.py"),
    ("Cache manager", "tests/test_agent/test_cache_manager.py"),
    ("Engine adapter", "tests/test_agent/test_engine_adapter.py"),
    ("Warmer", "tests/test_agent/test_warmer.py"),
    ("Scaler", "tests/test_operator/test_scaler.py"),
]
for name, path in modules:
    out = send(f"cd /workspace/kubbernetd && python -m pytest {path} -v --tb=line 2>&1", 60)
    passed = out.count("PASSED")
    failed = out.count("FAILED")
    errors = out.count("ERROR")
    tag = "[OK]" if failed == 0 and errors == 0 else "[FAIL]"
    print(f"  {tag} {name}: {passed} passed, {failed} failed, {errors} errors")

heading("4. GPU CHECK")
out = send("python3 -c \"import torch; print('CUDA:', torch.cuda.is_available())\" 2>&1", 15)
print(f"  {out[:100]}")
out = send("nvidia-smi --query-gpu=name,memory.free --format=csv,noheader 2>&1", 10)
print(f"  GPU: {out[:80]}")

heading("5. OPTIMIZER")
out = send('cd /workspace/kubbernetd && python3 -c "from kubbernetd.operator.optimizer import ColdStartProfiler; p=ColdStartProfiler(); p.start(); import time; time.sleep(0.05); p.end(); print(p.breakdown)"', 15)
print(f"  {out[:200]}")

chan.close()
client.close()
print(f"\n{'='*60}\nDONE\n{'='*60}")