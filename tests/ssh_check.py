import paramiko
import sys
import os
import time
import subprocess
import re

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

# Open an interactive shell session
chan = transport.open_session()
chan.get_pty(term="xterm", width=132, height=50)
chan.invoke_shell()
time.sleep(3)

def send_cmd(channel, cmd, timeout=20):
    """Send a command to the shell and capture output"""
    channel.send(cmd + "\n")
    time.sleep(1)
    output = b""
    start = time.time()
    prompt_pattern = b'root@[a-f0-9]+:.*?[$#]'
    
    while time.time() - start < timeout:
        if channel.recv_ready():
            output += channel.recv(65536)
            decoded = output.decode('utf-8', errors='replace')
            # Check for shell prompt
            if re.search(r'root@[a-f0-9]+:.*?[$#]', decoded, re.DOTALL):
                break
        time.sleep(0.2)
    
    result = output.decode('utf-8', errors='replace')
    # Remove ANSI escape codes
    result = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', result)
    result = re.sub(r'\x1b\][0-9;]*[^\x1b]*\x1b\\\\', '', result)
    result = re.sub(r'\x1b[?0-9;]*[a-zA-Z]', '', result)
    result = re.sub(r'\x07', '', result)
    # Remove the echo of the command itself
    lines = result.split('\n')
    filtered = []
    for line in lines:
        if cmd.strip() in line.strip():
            continue
        if 'root@' in line or 'RUNPOD' in line or 'Enjoy your Pod' in line:
            continue
        if line.strip():
            filtered.append(line.strip())
    return '\n'.join(filtered)

# Clear initial MOTD
time.sleep(2)
chan.recv(65536)

print("=== SYSTEM INFO ===")
for cmd in [
    "nvidia-smi --query-gpu=index,name,memory.total,memory.free,utilization.gpu --format=csv,noheader",
    "docker --version",
    "kubectl version --client 2>&1",
    "python3 --version",
    "pip3 --version",
    "free -h",
    "nproc",
    "lsblk -d -o NAME,SIZE,ROTA 2>&1",
    "df -h /",
]:
    result = send_cmd(chan, cmd)
    print(f"\n$ {cmd}")
    print(result)

chan.close()
client.close()
print("\n=== CONNECTED AND QUERIED ===")