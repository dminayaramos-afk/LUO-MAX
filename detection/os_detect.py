import os

def detect_os():
    info = {"id": "unknown", "name": "Linux Desconocido", "version": "N/A", "kernel": os.uname().release}
    if os.path.exists("/etc/os-release"):
        with open("/etc/os-release", "r") as f:
            lines = f.readlines()
            os_data = {}
            for line in lines:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    os_data[k] = v.strip('"')
            info["id"] = os_data.get("ID", "unknown")
            info["name"] = os_data.get("PRETTY_NAME", os_data.get("NAME", "Linux"))
            info["version"] = os_data.get("VERSION_ID", "N/A")
    return info
