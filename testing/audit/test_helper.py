import subprocess, json, sys

pod = subprocess.run(
    ["kubectl", "get", "pod", "-l", "app=long-request", "-o", "name"],
    capture_output=True, text=True, check=False
).stdout.strip().split("\n")[0]

if not pod:
    print("NO_POD")
    sys.exit(1)

print(f"POD: {pod}")

ip = subprocess.run(
    ["kubectl", "get", pod, "-o", "jsonpath={.status.podIP}"],
    capture_output=True, text=True, check=False
).stdout.strip()

print(f"IP: {ip}")

# Test via exec
result = subprocess.run(
    ["kubectl", "exec", pod, "--", "python3", "-c",
     "import http.client; c=http.client.HTTPConnection('localhost',80); c.request('GET','/work?seconds=1'); r=c.getresponse(); print(r.status, r.read().decode())"],
    capture_output=True, text=True, timeout=15
)
print(f"DIRECT: exit={result.returncode} stdout={result.stdout.strip()} stderr={result.stderr[:200]}")
