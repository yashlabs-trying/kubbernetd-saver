import subprocess

pod = subprocess.run(
    ["kubectl", "get", "pod", "-l", "app=long-request", "-o", "name"],
    capture_output=True, text=True, check=False
).stdout.strip().split("\n")[0]

script = """
import sys
sys.path.insert(0, '/app')
from server import build_app
app = build_app('long-request')
for r in app.router.routes():
    print(r.resource, r.method)
for r in app.router.resources():
    print('RESOURCE:', r.canonical)
"""

result = subprocess.run(
    ["kubectl", "exec", pod, "--", "python3", "-c", script],
    capture_output=True, text=True, timeout=15
)
print("OUT:", result.stdout.strip())
print("ERR:", result.stderr[:300] if result.stderr else "")
