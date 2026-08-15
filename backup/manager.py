import os
import shutil
import json
from datetime import datetime

BACKUP_DIR = "/tmp/luo/backups"
LOG_FILE = "/tmp/luo/history.log"

class BackupManager:
    def __init__(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        os.makedirs("/tmp/luo", exist_ok=True)

    def create_backup(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        b_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}")
        os.makedirs(b_path, exist_ok=True)
        
        meta = {"timestamp": timestamp}
        with open(os.path.join(b_path, "metadata.json"), "w") as f:
            json.dump(meta, f)
            
        self._log(f"Backup creado en {b_path}")
        return b_path

    def restore_last(self):
        if not os.path.exists(BACKUP_DIR):
            print("No hay backups disponibles.")
            return False
        backups = sorted(os.listdir(BACKUP_DIR))
        if not backups:
            print("No se encontraron respaldos.")
            return False
        latest = os.path.join(BACKUP_DIR, backups[-1])
        print(f"Restaurando desde {latest}...")
        self._log(f"Sistema restaurado desde {latest}")
        return True

    def _log(self, message):
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now()}] {message}\n")
