import os
import shutil

def detect_hardware():
    hw = {
        "cpu": "Desconocida",
        "ram_gb": 0,
        "storage_type": "Desconocido",
        "gpu": "Desconocida",
        "network": "Desconocida",
        "audio": "Desconocido"
    }
    
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    hw["cpu"] = line.split(":")[1].strip()
                    break

    if os.path.exists("/proc/meminfo"):
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    kb = int(line.split()[1])
                    hw["ram_gb"] = round(kb / (1024 * 1024), 2)
                    break

    if shutil.which("lsblk"):
        import subprocess
        try:
            res = subprocess.check_output(["lsblk", "-d", "-o", "NAME,ROTA"], text=True)
            if "0" in res:
                hw["storage_type"] = "SSD / NVMe"
            else:
                hw["storage_type"] = "HDD"
        except Exception:
            pass

    return hw
