import shutil
import subprocess

class GamingOptimizer:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def check_gamemode(self):
        """Verifica si gamemode está disponible en el sistema."""
        return shutil.which("gamemoderun") is not None

    def optimize_gaming_profile(self):
        """Configura perfiles orientados a baja latencia para juegos."""
        if self.check_gamemode():
            if self.verbose:
                print("✓ GameMode detectado y listo para ser utilizado en lanzadores de juegos.")
            return True
        else:
            if self.verbose:
                print("⚠ GameMode no está instalado en el sistema. Puedes instalarlo con tu gestor de paquetes (ej. apt install gamemode).")
            return False
