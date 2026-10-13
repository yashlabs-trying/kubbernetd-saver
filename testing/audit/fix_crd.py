with open('/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/config/crd.yaml', 'r') as f:
    content = f.read()
content = content.replace("cpuRAM:\n                      type: string\n                      default: 0", "cpuRAM:\n                      type: string\n                      default: \"0\"")
with open('/Users/harshvardhansinghshekhawat/ignite/kubbernetd-saver/config/crd.yaml', 'w') as f:
    f.write(content)
print("FIXED")
