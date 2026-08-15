import sys
from detection.os_detect import detect_os
from detection.hardware_detect import detect_hardware
from backup.manager import BackupManager
from optimization.optimizer import SystemOptimizer
from optimization.cleaner import SystemCleaner
from gaming.gamemode import GamingOptimizer
from persistence.service import PersistenceManager

class OptimizationEngine:
    def __init__(self, verbose=False, live=False, quiet=False):
        self.verbose = verbose
        self.live = live
        self.quiet = quiet
        self.backup_mgr = BackupManager()
        self.optimizer = SystemOptimizer(verbose=verbose)
        self.cleaner = SystemCleaner(verbose=verbose)
        self.gaming_opt = GamingOptimizer(verbose=verbose)
        self.persistence_mgr = PersistenceManager(verbose=verbose)

    def optimize(self, auto=False, gaming=False, persistence=False):
        if not self.quiet:
            print("🐧 Linux Universal Optimizer (LUO)\n")
            print("Analizando sistema...")

        os_info = detect_os()
        hw_info = detect_hardware()

        if not self.quiet:
            print(f"✓ Linux detectado: {os_info['name']}")
            print(f"✓ Kernel: {os_info['kernel']}")
            print(f"✓ CPU: {hw_info['cpu']}")
            print(f"✓ RAM: {hw_info['ram_gb']} GB")
            print(f"✓ Almacenamiento: {hw_info['storage_type']}")
            print("\nCreando backup de seguridad...")

        self.backup_mgr.create_backup()

        if not self.quiet:
            print("✓ Backup creado exitosamente.")
            print("\nAplicando optimizaciones y limpieza profunda...")

        # 1. Aplicar sysctl y TRIM
        self.optimizer.apply_sysctl_optimizations()
        if hw_info['storage_type'] == "SSD / NVMe":
            self.optimizer.enable_trim()
            if not self.quiet:
                print("  → TRIM habilitado para SSD/NVMe")

        # 2. Limpieza de RAM, temporales y paquetes huérfanos
        self.cleaner.clear_ram_cache()
        self.cleaner.clean_temp_files()
        self.cleaner.update_and_clean_packages()
        if not self.quiet:
            print("  → Caché de RAM, archivos temporales y paquetes huérfanos limpiados")

        # 3. Gaming y Persistencia opcionales
        if gaming or auto:
            self.gaming_opt.optimize_gaming_profile()
            if not self.quiet:
                print("  → Perfil de gaming evaluado")

        if persistence:
            self.persistence_mgr.create_systemd_service()
            if not self.quiet:
                print("  → Servicio de persistencia configurado")

        if not self.quiet:
            print("\n✓ ¡Optimización y limpieza completadas con éxito!")

    def restore(self):
        self.backup_mgr.restore_last()

    def status(self):
        os_info = detect_os()
        hw_info = detect_hardware()
        print("=== Estado del Sistema - LUO ===")
        print(f"SO: {os_info['name']} (Kernel {os_info['kernel']})")
        print(f"CPU: {hw_info['cpu']}")
        print(f"RAM: {hw_info['ram_gb']} GB")
        print(f"Almacenamiento: {hw_info['storage_type']}")

    def history(self):
        log_path = "/tmp/luo/history.log"
        try:
            with open(log_path, "r") as f:
                print(f.read())
        except FileNotFoundError:
            print("No hay historial de optimizaciones registrado.")
