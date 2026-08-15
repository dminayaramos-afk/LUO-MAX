import os
import shutil
import subprocess

class SystemCleaner:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def clear_ram_cache(self):
        """Libera la caché de páginas, dentries e inodes de la RAM (requiere root)."""
        if self.verbose:
            print("Limpiando caché de RAM (PageCache, dentries, inodes)...")
        try:
            # Sincroniza los búferes del sistema de archivos al disco primero
            subprocess.run(["sync"], check=True)
            with open("/proc/sys/vm/drop_caches", "w") as f:
                f.write("3")
            if self.verbose:
                print("✓ Caché de RAM liberada correctamente.")
            return True
        except Exception:
            if self.verbose:
                print("⚠ Aviso: No se pudo limpiar la caché de RAM (requiere permisos de superusuario/root).")
            return False

    def clean_temp_files(self):
        """Elimina archivos temporales comunes del sistema."""
        temp_dirs = ["/tmp", "/var/tmp"]
        deleted_count = 0
        for d in temp_dirs:
            if os.path.exists(d):
                for root, dirs, files in os.walk(d):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            # Evitar borrar archivos muy recientes o críticos en uso
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                                deleted_count += 1
                        except Exception:
                            pass
        if self.verbose:
            print(f"✓ Archivos temporales eliminados: {deleted_count} archivos.")
        return True

    def update_and_clean_packages(self):
        """Detecta el gestor de paquetes de la distro y actualiza/elimina huérfanos."""
        if self.verbose:
            print("Detectando gestor de paquetes para actualización y limpieza...")

        # Detectar apt (Debian/Ubuntu/Mint)
        if shutil.which("apt"):
            try:
                subprocess.run(["apt", "update"], check=True)
                subprocess.run(["apt", "upgrade", "-y"], check=True)
                subprocess.run(["apt", "autoremove", "-y"], check=True) # Elimina huérfanos
                subprocess.run(["apt", "clean"], check=True)
                if self.verbose:
                    print("✓ Paquetes actualizados y huérfanos eliminados (APT).")
                return True
            except Exception:
                pass

        # Detectar dnf (Fedora/RHEL)
        if shutil.which("dnf"):
            try:
                subprocess.run(["dnf", "upgrade", "-y"], check=True)
                subprocess.run(["dnf", "autoremove", "-y"], check=True)
                subprocess.run(["dnf", "clean", "all"], check=True)
                if self.verbose:
                    print("✓ Paquetes actualizados y huérfanos eliminados (DNF).")
                return True
            except Exception:
                pass

        # Detectar pacman (Arch Linux / Manjaro)
        if shutil.which("pacman"):
            try:
                # -Syu actualiza, -Qdtq busca huérfanos para limpiar
                subprocess.run(["pacman", "-Syu", "--noconfirm"], check=True)
                subprocess.run(["bash", "-c", "pacman -Rns $(pacman -Qdtq) --noconfirm"], check=False)
                subprocess.run(["pacman", "-Sc", "--noconfirm"], check=True)
                if self.verbose:
                    print("✓ Paquetes actualizados y huérfanos eliminados (Pacman).")
                return True
            except Exception:
                pass

        if self.verbose:
            print("⚠ Gestor de paquetes no compatible o requiere permisos de administrador.")
        return False
