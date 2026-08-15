import os
import subprocess

class SystemOptimizer:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def apply_sysctl_optimizations(self):
        """Aplica configuraciones seguras en sysctl para mejorar el rendimiento de red y memoria."""
        sysctl_conf = "/etc/sysctl.d/99-luo-performance.conf"
        content = """# Optimizaciones de rendimiento - Linux Universal Optimizer (LUO)
vm.swappiness = 10
vm.vfs_cache_pressure = 50
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
"""
        try:
            # Asegurar que el directorio existe (puede fallar si no hay permisos)
            os.makedirs(os.path.dirname(sysctl_conf), exist_ok=True)
            with open(sysctl_conf, "w") as f:
                f.write(content)
            if self.verbose:
                print(f"✓ Configuración sysctl creada en {sysctl_conf}")
            return True
        except (PermissionError, FileNotFoundError, OSError):
            if self.verbose:
                print("⚠ Aviso: No se pudo escribir en /etc/sysctl.d/ (se requieren permisos de administrador o estás en un entorno protegido).")
            return False

    def enable_trim(self):
        """Habilita y ejecuta fstrim si hay SSDs."""
        if self.verbose:
            print("Ejecutando TRIM en unidades compatibles...")
        try:
            subprocess.run(["fstrim", "-av"], check=True)
            return True
        except Exception:
            if self.verbose:
                print("⚠ Aviso: fstrim no se pudo ejecutar (puede requerir privilegios o no estar soportado).")
            return False
