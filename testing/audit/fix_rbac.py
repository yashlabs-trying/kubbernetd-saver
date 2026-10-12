with open("/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/config/operator-rbac.yaml", "r") as f:
    content = f.read()
content = content.replace('verbs: ["get", "list"]', 'verbs: ["get", "list", "watch"]')
with open("/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/config/operator-rbac.yaml", "w") as f:
    f.write(content)
print("FIXED")
