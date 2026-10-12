import subprocess

pod = subprocess.run(
    ["kubectl", "get", "pod", "-l", "app=long-request", "-o", "name"],
    capture_output=True, text=True, check=False
).stdout.strip().split("\n")[0]

# Check running process args
result = subprocess.run(
    ["kubectl", "exec", pod, "--", "ps", "aux"],
    capture_output=True, text=True, timeout=15
)
print("PS:", result.stdout.strip())

# Check env
result2 = subprocess.run(
    ["kubectl", "exec", pod, "--", "env"],
    capture_output=True, text=True, timeout=15
)
for line in result2.stdout.strip().split("\n"):
    if "E2E" in line or "HELPER" in line or "MODE" in line:
        print("ENV:", line)
