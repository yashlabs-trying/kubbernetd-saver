filepath = "/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/kubbernetd/common/types.py"
with open(filepath, "r") as f:
    content = f.read()

# Fix the ProxyConfig env var names to avoid Kubernetes service env collision
content = content.replace(
    'listen_port: int = int(environ.get("KUBBERNETD_PROXY_PORT", "8080"))',
    'listen_port: int = int(environ.get("KUBBERNETD_PROXY_LISTEN_PORT", "8080"))'
)
content = content.replace(
    'upstream_port: int = int(environ.get("KUBBERNETD_PROXY_PORT", "8080"))',
    'upstream_port: int = int(environ.get("KUBBERNETD_UPSTREAM_PORT", "8080"))'
)

with open(filepath, "w") as f:
    f.write(content)
print("FIXED")
