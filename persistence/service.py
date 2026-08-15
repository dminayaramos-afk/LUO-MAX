import os

class PersistenceManager:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def create_systemd_service(self):
        """Crea un servicio systemd para aplicar las optimizaciones al iniciar el sistema."""
        service_content = """[Unit]
Description=Linux Universal Optimizer Startup Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/luo optimize --auto

[Install]
WantedBy=multi-user.target
"""
        service_path = "/tmp/luo-optimizer.service"
        try:
            with open(service_path, "w") as f:
                f.write(service_content)
            if self.verbose:
                print(f"✓ Servicio systemd generado de prueba en {service_path}")
            return True
        except Exception as e:
            if self.verbose:
                print(f"⚠ Error al crear el servicio: {e}")
            return False
