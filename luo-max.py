#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
 LUO-MAX · Linux Universal Optimizer — Modo TURBO/OVERCLOCK
==============================================================================

Versión de archivo único de "Linux Universal Optimizer" (LUO), inspirada en
el funcionamiento de GameMode (feralinteractive/gamemode): un demonio
ligero que, en lugar de activarse solo mientras corre un juego, mantiene
el equipo TODO EL TIEMPO en el perfil de máximo rendimiento posible según
el hardware detectado (CPU, GPU integrada/dedicada, disco), y de forma
periódica libera RAM y borra archivos temporales para que el sistema no
se degrade con el uso continuo.

Filosofía (igual que GameMode, pero permanente y sin límite de fabricante):
  1. Detectar el hardware real de CADA equipo (no aplicar nada "a ciegas").
     Funciona igual en un portátil Intel+NVIDIA Optimus, un equipo AMD
     (CPU Ryzen + GPU amdgpu), un mini-PC ARM, o un servidor sin GPU/batería.
  2. Empujar CPU/GPU al perfil de mayor rendimiento que ESE hardware
     concreto soporte (cada rama de código comprueba antes de tocar nada).
  3. Vigilar temperatura y bajar el perfil automáticamente si hay riesgo
     de sobrecalentamiento (protección real, sobre todo en portátiles).
  4. Limpiar caché de RAM y temporales cada N minutos (5 por defecto).
  5. Guardar un backup del estado original para poder revertir con
     `restore` en cualquier momento.

Uso rápido:
  sudo python3 luo-max.py apply              # aplica el modo turbo una vez
  sudo python3 luo-max.py daemon             # aplica + vigila + limpia cada 5 min (foreground)
  sudo python3 luo-max.py daemon --extreme   # además bloquea la CPU siempre al máximo (más calor)
  sudo python3 luo-max.py status             # muestra el estado actual
  sudo python3 luo-max.py restore            # revierte todo a los valores originales
  sudo python3 luo-max.py stop               # detiene el demonio en background
  sudo python3 luo-max.py install-service    # instala servicio systemd persistente
  sudo python3 luo-max.py uninstall-service  # lo desinstala y restaura

No requiere dependencias externas, solo Python 3 estándar.
==============================================================================
"""

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

# ------------------------------------------------------------------------
# Rutas y constantes
# ------------------------------------------------------------------------

STATE_DIR = "/var/lib/luo-max" if os.geteuid() == 0 else "/tmp/luo-max"
BACKUP_FILE = os.path.join(STATE_DIR, "backup.json")
PID_FILE = os.path.join(STATE_DIR, "daemon.pid")
LOG_FILE = os.path.join(STATE_DIR, "luo-max.log")
SYSCTL_CONF = "/etc/sysctl.d/99-luo-max.conf"
SERVICE_PATH = "/etc/systemd/system/luo-max.service"
BIN_INSTALL_PATH = "/usr/local/bin/luo-max"

DEFAULT_CLEAN_INTERVAL = 300      # 5 minutos
DEFAULT_TEMP_LIMIT_C = 85         # techo térmico seguro por defecto
DEFAULT_TEMP_RECOVER_C = 75       # temperatura a la que se reactiva turbo tras enfriar

CPU_ROOT = "/sys/devices/system/cpu"
INTEL_PSTATE = f"{CPU_ROOT}/intel_pstate"
CPUFREQ_BOOST = f"{CPU_ROOT}/cpufreq/boost"

TEMP_DIRS = ["/tmp", "/var/tmp"]
TEMP_MIN_AGE_SECONDS = 300  # no tocar archivos con menos de 5 min de antigüedad


# ------------------------------------------------------------------------
# Utilidades base
# ------------------------------------------------------------------------

def ensure_state_dir():
    os.makedirs(STATE_DIR, exist_ok=True)


def log(msg, verbose=True, quiet=False):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if not quiet:
        print(msg)
    try:
        ensure_state_dir()
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_root():
    return os.geteuid() == 0


def read_file(path, default=None):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def write_file(path, value):
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True
    except Exception:
        return False


def run(cmd, check=False):
    try:
        return subprocess.run(cmd, check=check, capture_output=True, text=True)
    except Exception:
        return None


def which(binary):
    from shutil import which as _which
    return _which(binary)


# ------------------------------------------------------------------------
# Detección de hardware
# ------------------------------------------------------------------------

def detect_os():
    info = {"name": "Linux Desconocido", "kernel": os.uname().release}
    if os.path.exists("/etc/os-release"):
        data = {}
        for line in read_file("/etc/os-release", "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip('"')
        info["name"] = data.get("PRETTY_NAME", data.get("NAME", "Linux"))
    return info


def detect_cpu():
    cpu = {"model": "Desconocida", "cores": os.cpu_count() or 1,
           "vendor": "unknown", "has_intel_pstate": os.path.isdir(INTEL_PSTATE),
           "has_boost": os.path.exists(CPUFREQ_BOOST)}
    for line in read_file("/proc/cpuinfo", "").splitlines():
        if "model name" in line:
            cpu["model"] = line.split(":", 1)[1].strip()
            break
    if "intel" in cpu["model"].lower():
        cpu["vendor"] = "intel"
    elif "amd" in cpu["model"].lower():
        cpu["vendor"] = "amd"
    return cpu


def detect_gpus():
    """Detecta cualquier combinación de GPU presente: Intel integrada,
    AMD (amdgpu) integrada o dedicada, y NVIDIA dedicada (incluye setups
    Optimus/PRIME con una o varias GPUs)."""
    gpus = {"intel_cards": [], "amd_cards": [], "nvidia": False, "nvidia_count": 0}

    for path in glob.glob("/sys/class/drm/card*/gt_max_freq_mhz"):
        gpus["intel_cards"].append(os.path.dirname(path))

    for path in glob.glob("/sys/class/drm/card*/device/power_dpm_force_performance_level"):
        gpus["amd_cards"].append(os.path.dirname(path))

    if which("nvidia-smi") is not None:
        q = run(["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"])
        count = len(q.stdout.strip().splitlines()) if (q and q.returncode == 0 and q.stdout.strip()) else 1
        gpus["nvidia"] = True
        gpus["nvidia_count"] = count

    return gpus


def detect_power_source():
    """Detecta si el dispositivo corre con batería o conectado a corriente.
    Devuelve None en equipos sin batería (sobremesa, servidor, etc.)."""
    for bat in glob.glob("/sys/class/power_supply/BAT*/status"):
        status = read_file(bat, "")
        if status:
            return status  # "Charging", "Discharging", "Full", ...
    return None


def detect_storage():
    disks = {"ssd": [], "hdd": []}
    res = run(["lsblk", "-d", "-n", "-o", "NAME,ROTA"])
    if res and res.returncode == 0:
        for line in res.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                name, rota = parts
                (disks["hdd"] if rota == "1" else disks["ssd"]).append(name)
    return disks


def detect_ram_gb():
    for line in read_file("/proc/meminfo", "").splitlines():
        if "MemTotal" in line:
            kb = int(line.split()[1])
            return round(kb / (1024 * 1024), 2)
    return 0.0


def get_temperatures():
    """Devuelve la temperatura más alta detectada entre todas las zonas térmicas (°C)."""
    temps = []
    for zone in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        raw = read_file(zone)
        if raw and raw.lstrip("-").isdigit():
            temps.append(int(raw) / 1000.0)
    return max(temps) if temps else None


# ------------------------------------------------------------------------
# Backup / Restore (para poder revertir el "overclock" con seguridad)
# ------------------------------------------------------------------------

def load_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_backup(data):
    ensure_state_dir()
    with open(BACKUP_FILE, "w") as f:
        json.dump(data, f, indent=2)


def snapshot_current_state(cpu, gpus):
    """Guarda el estado ANTES de tocar nada, solo si no existe ya un backup."""
    if load_backup() is not None:
        return  # ya hay un backup previo: no lo pisamos
    snap = {"timestamp": datetime.now().isoformat(), "governors": {}, "intel_pstate": {},
            "boost": None, "intel_gpu": {}, "amd_gpu": {},
            "sysctl_existed": os.path.exists(SYSCTL_CONF)}

    for gov_path in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq/scaling_governor"):
        snap["governors"][gov_path] = read_file(gov_path)

    if cpu["has_intel_pstate"]:
        snap["intel_pstate"]["no_turbo"] = read_file(f"{INTEL_PSTATE}/no_turbo")
        snap["intel_pstate"]["min_perf_pct"] = read_file(f"{INTEL_PSTATE}/min_perf_pct")
        snap["intel_pstate"]["max_perf_pct"] = read_file(f"{INTEL_PSTATE}/max_perf_pct")

    if cpu["has_boost"]:
        snap["boost"] = read_file(CPUFREQ_BOOST)

    for card_dir in gpus["intel_cards"]:
        snap["intel_gpu"][card_dir] = read_file(os.path.join(card_dir, "gt_min_freq_mhz"))

    for card_dir in gpus["amd_cards"]:
        snap["amd_gpu"][card_dir] = read_file(
            os.path.join(card_dir, "power_dpm_force_performance_level"))

    save_backup(snap)


# ------------------------------------------------------------------------
# Aplicar rendimiento máximo (CPU)
# ------------------------------------------------------------------------

def apply_cpu_governor_performance(verbose):
    changed = 0
    for gov_path in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq/scaling_governor"):
        available = read_file(gov_path.replace("scaling_governor", "scaling_available_governors"), "")
        target = "performance" if "performance" in available else None
        if target and write_file(gov_path, target):
            changed += 1
    if verbose:
        log(f"  → Governor de CPU puesto en 'performance' en {changed} núcleo(s).")
    return changed > 0


def apply_intel_turbo(cpu, extreme, verbose):
    if not cpu["has_intel_pstate"]:
        return False
    write_file(f"{INTEL_PSTATE}/no_turbo", 0)               # turbo boost activado
    write_file(f"{INTEL_PSTATE}/max_perf_pct", 100)          # techo de rendimiento al 100%
    if extreme:
        # Modo extremo: no deja que el CPU baje de frecuencia nunca (más calor/consumo).
        write_file(f"{INTEL_PSTATE}/min_perf_pct", 100)
    else:
        write_file(f"{INTEL_PSTATE}/min_perf_pct", 20)
    if verbose:
        modo = "extremo (min=100%)" if extreme else "equilibrado (min=20%, max=100%, turbo ON)"
        log(f"  → Intel P-State configurado en modo {modo}.")
    return True


def apply_generic_boost(cpu, verbose):
    if not cpu["has_boost"]:
        return False
    write_file(CPUFREQ_BOOST, 1)
    if verbose:
        log("  → Boost genérico de CPU (AMD/acpi-cpufreq) activado.")
    return True


def apply_energy_policy_performance(verbose):
    if which("cpupower"):
        run(["cpupower", "set", "-b", "1"])
        run(["cpupower", "frequency-set", "-g", "performance"])
        if verbose:
            log("  → cpupower ajustado a política de rendimiento.")
    elif which("x86_energy_perf_policy"):
        run(["x86_energy_perf_policy", "performance"])
        if verbose:
            log("  → x86_energy_perf_policy ajustado a 'performance'.")


def apply_max_cpu_frequency(verbose):
    """Sube scaling_max_freq al máximo físico que soporta cada núcleo."""
    changed = 0
    for cpu_dir in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq"):
        cpuinfo_max = read_file(os.path.join(cpu_dir, "cpuinfo_max_freq"))
        if cpuinfo_max and write_file(os.path.join(cpu_dir, "scaling_max_freq"), cpuinfo_max):
            changed += 1
    if verbose and changed:
        log(f"  → Frecuencia máxima habilitada en {changed} núcleo(s).")


# ------------------------------------------------------------------------
# Aplicar rendimiento máximo (GPU)
# ------------------------------------------------------------------------

def apply_gpu_max(gpus, verbose):
    # --- GPU integrada Intel: fuerza la frecuencia mínima a la máxima soportada ---
    for card_dir in gpus["intel_cards"]:
        gt_max = read_file(os.path.join(card_dir, "gt_max_freq_mhz"))
        if gt_max:
            write_file(os.path.join(card_dir, "gt_min_freq_mhz"), gt_max)
            if verbose:
                log(f"  → GPU Intel ({card_dir}) fijada a {gt_max} MHz constantes.")

    # --- GPU AMD (amdgpu), integrada o dedicada: fuerza el estado de rendimiento más alto ---
    for card_dir in gpus["amd_cards"]:
        perf_path = os.path.join(card_dir, "power_dpm_force_performance_level")
        if write_file(perf_path, "high"):
            if verbose:
                log(f"  → GPU AMD ({card_dir}) forzada a nivel de rendimiento 'high'.")
        # Si el driver expone estados manuales de reloj (pp_dpm_sclk / pp_dpm_mclk),
        # selecciona explícitamente el estado más alto disponible de cada uno.
        for clk_file in ("pp_dpm_sclk", "pp_dpm_mclk"):
            clk_path = os.path.join(card_dir, clk_file)
            states = read_file(clk_path, "")
            if states:
                lines = [l for l in states.splitlines() if l.strip()]
                if lines:
                    highest_id = lines[-1].strip().split(":")[0]
                    write_file(clk_path, highest_id)

    # --- GPU(s) NVIDIA dedicada(s): persistence mode + límite de potencia al máximo, una por una ---
    if gpus["nvidia"]:
        run(["nvidia-smi", "-pm", "1"])
        for idx in range(gpus.get("nvidia_count", 1)):
            q = run(["nvidia-smi", "-i", str(idx), "--query-gpu=power.max_limit",
                     "--format=csv,noheader,nounits"])
            if q and q.returncode == 0 and q.stdout.strip():
                try:
                    max_watts = q.stdout.strip().splitlines()[0].strip()
                    r = run(["nvidia-smi", "-i", str(idx), "-pl", max_watts])
                    if verbose and r and r.returncode == 0:
                        log(f"  → GPU NVIDIA #{idx}: persistence mode ON, límite de potencia a {max_watts} W.")
                    elif verbose:
                        log(f"  ⚠ GPU NVIDIA #{idx} detectada, pero este chip no admite ajustar el power "
                            f"limit (normal en GPUs móviles antiguas tipo Kepler/GT6xx-8xx).")
                except Exception:
                    pass
            else:
                if verbose:
                    log(f"  ⚠ nvidia-smi no pudo consultar límites de potencia en la GPU #{idx}.")


# ------------------------------------------------------------------------
# Disco / E-S / red / memoria
# ------------------------------------------------------------------------

def apply_storage_tuning(disks, verbose):
    if disks["ssd"] and which("fstrim"):
        run(["fstrim", "-av"])
        if verbose:
            log("  → TRIM ejecutado en unidades SSD/NVMe.")
    for name in disks["ssd"]:
        sched_path = f"/sys/block/{name}/queue/scheduler"
        avail = read_file(sched_path, "")
        for pref in ("none", "mq-deadline"):
            if pref in avail:
                write_file(sched_path, pref)
                break
    for name in disks["hdd"]:
        sched_path = f"/sys/block/{name}/queue/scheduler"
        avail = read_file(sched_path, "")
        if "bfq" in avail:
            write_file(sched_path, "bfq")


def apply_sysctl_max(verbose):
    content = """# LUO-MAX: perfil de rendimiento máximo (memoria + red)
vm.swappiness = 1
vm.vfs_cache_pressure = 50
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5
kernel.sched_autogroup_enabled = 0
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
net.core.netdev_max_backlog = 16384
"""
    try:
        os.makedirs(os.path.dirname(SYSCTL_CONF), exist_ok=True)
        with open(SYSCTL_CONF, "w") as f:
            f.write(content)
        run(["sysctl", "-p", SYSCTL_CONF])
        if verbose:
            log(f"  → Ajustes sysctl de rendimiento aplicados ({SYSCTL_CONF}).")
        return True
    except Exception:
        if verbose:
            log("  ⚠ No se pudo escribir sysctl (¿faltan permisos de root?).")
        return False


# ------------------------------------------------------------------------
# Limpieza periódica (cada N minutos)
# ------------------------------------------------------------------------

def clear_ram_cache(verbose):
    try:
        run(["sync"])
        write_file("/proc/sys/vm/drop_caches", 3)
        if verbose:
            log("  → Caché de RAM (PageCache/dentries/inodes) liberada.")
        return True
    except Exception:
        return False


def clean_temp_files(verbose, min_age=TEMP_MIN_AGE_SECONDS):
    now = time.time()
    deleted, freed_bytes = 0, 0
    for d in TEMP_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for name in files:
                fpath = os.path.join(root, name)
                try:
                    st = os.lstat(fpath)
                    if now - st.st_mtime < min_age:
                        continue  # respeta archivos recién creados/en uso
                    size = st.st_size
                    os.remove(fpath)
                    deleted += 1
                    freed_bytes += size
                except Exception:
                    continue
    if verbose:
        log(f"  → Limpieza de temporales: {deleted} archivo(s), {freed_bytes / (1024*1024):.1f} MB liberados.")
    return deleted, freed_bytes


def clean_cycle(verbose):
    clear_ram_cache(verbose)
    clean_temp_files(verbose)


# ------------------------------------------------------------------------
# Seguridad térmica
# ------------------------------------------------------------------------

def thermal_guard(cpu, extreme, temp_limit, temp_recover, throttled_state, verbose):
    """Si la temperatura es demasiado alta, baja el perfil temporalmente.
    Si ya se había bajado y la temperatura se recuperó, vuelve a modo turbo."""
    temp = get_temperatures()
    if temp is None:
        return throttled_state

    if not throttled_state and temp >= temp_limit:
        log(f"  ⚠ Temperatura alta detectada ({temp:.1f}°C ≥ {temp_limit}°C): "
            f"bajando a modo seguro para proteger el hardware.", quiet=not verbose)
        for gov_path in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq/scaling_governor"):
            available = read_file(gov_path.replace("scaling_governor", "scaling_available_governors"), "")
            fallback = "powersave" if "powersave" in available else "ondemand"
            if fallback in available:
                write_file(gov_path, fallback)
        if cpu["has_intel_pstate"]:
            write_file(f"{INTEL_PSTATE}/no_turbo", 1)
        return True

    if throttled_state and temp <= temp_recover:
        log(f"  ✓ Temperatura normalizada ({temp:.1f}°C ≤ {temp_recover}°C): "
            f"reactivando modo turbo.", quiet=not verbose)
        apply_cpu_governor_performance(verbose)
        apply_intel_turbo(cpu, extreme, verbose)
        return False

    return throttled_state


# ------------------------------------------------------------------------
# Ciclo de aplicación completo
# ------------------------------------------------------------------------

def apply_all(extreme=False, verbose=True, quiet=False):
    if not is_root():
        log("❌ Este comando necesita permisos de root (usa sudo).", quiet=quiet)
        sys.exit(1)

    os_info = detect_os()
    cpu = detect_cpu()
    gpus = detect_gpus()
    disks = detect_storage()
    ram_gb = detect_ram_gb()

    if not quiet:
        log("🚀 LUO-MAX — aplicando perfil de rendimiento máximo\n", quiet=quiet)
        log(f"✓ SO: {os_info['name']} (kernel {os_info['kernel']})", quiet=quiet)
        log(f"✓ CPU: {cpu['model']} ({cpu['cores']} hilos, vendor={cpu['vendor']})", quiet=quiet)
        log(f"✓ RAM: {ram_gb} GB", quiet=quiet)
        log(f"✓ GPU Intel: {'sí' if gpus['intel_cards'] else 'no'} | "
            f"AMD: {'sí' if gpus['amd_cards'] else 'no'} | "
            f"NVIDIA: {'sí (' + str(gpus['nvidia_count']) + ')' if gpus['nvidia'] else 'no'}", quiet=quiet)
        log(f"✓ Discos SSD/NVMe: {disks['ssd'] or 'ninguno'} | HDD: {disks['hdd'] or 'ninguno'}", quiet=quiet)
        power = detect_power_source()
        if power:
            log(f"✓ Alimentación: {power} (dispositivo con batería)", quiet=quiet)

    power = detect_power_source()
    if power == "Discharging" and not quiet:
        log("⚠ El dispositivo está funcionando con batería. El modo turbo aumentará el "
            "consumo notablemente; conéctalo a corriente si vas a usarlo un rato largo.",
            quiet=quiet)

    snapshot_current_state(cpu, gpus)

    apply_cpu_governor_performance(verbose and not quiet)
    apply_intel_turbo(cpu, extreme, verbose and not quiet)
    apply_generic_boost(cpu, verbose and not quiet)
    apply_energy_policy_performance(verbose and not quiet)
    apply_max_cpu_frequency(verbose and not quiet)
    apply_gpu_max(gpus, verbose and not quiet)
    apply_storage_tuning(disks, verbose and not quiet)
    apply_sysctl_max(verbose and not quiet)
    clean_cycle(verbose and not quiet)

    if not quiet:
        log("\n✓ Perfil TURBO aplicado. El equipo está funcionando al máximo rendimiento "
            "que su hardware permite.", quiet=quiet)
    return cpu, gpus


# ------------------------------------------------------------------------
# Restaurar valores originales
# ------------------------------------------------------------------------

def restore_all(verbose=True):
    if not is_root():
        log("❌ Este comando necesita permisos de root (usa sudo).")
        sys.exit(1)

    snap = load_backup()
    if snap is None:
        log("⚠ No hay un backup guardado. Aplicando valores seguros por defecto (ondemand/powersave).")
        for gov_path in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq/scaling_governor"):
            available = read_file(gov_path.replace("scaling_governor", "scaling_available_governors"), "")
            for pref in ("ondemand", "powersave", "schedutil"):
                if pref in available:
                    write_file(gov_path, pref)
                    break
        if os.path.exists(SYSCTL_CONF):
            os.remove(SYSCTL_CONF)
            run(["sysctl", "--system"])
        log("✓ Sistema devuelto a un perfil de energía estándar.")
        return

    for path, value in snap.get("governors", {}).items():
        if value:
            write_file(path, value)

    ip = snap.get("intel_pstate", {})
    for key, sysfs_name in (("no_turbo", "no_turbo"), ("min_perf_pct", "min_perf_pct"),
                             ("max_perf_pct", "max_perf_pct")):
        if ip.get(key) is not None:
            write_file(f"{INTEL_PSTATE}/{sysfs_name}", ip[key])

    if snap.get("boost") is not None:
        write_file(CPUFREQ_BOOST, snap["boost"])

    for card_dir, value in snap.get("intel_gpu", {}).items():
        if value:
            write_file(os.path.join(card_dir, "gt_min_freq_mhz"), value)

    for card_dir, value in snap.get("amd_gpu", {}).items():
        if value:
            write_file(os.path.join(card_dir, "power_dpm_force_performance_level"), value)

    if not snap.get("sysctl_existed", False) and os.path.exists(SYSCTL_CONF):
        os.remove(SYSCTL_CONF)
        run(["sysctl", "--system"])

    if os.path.exists(BACKUP_FILE):
        os.remove(BACKUP_FILE)

    log("✓ Sistema restaurado a los valores previos a aplicar LUO-MAX.")


# ------------------------------------------------------------------------
# Estado
# ------------------------------------------------------------------------

def print_status():
    cpu = detect_cpu()
    gpus = detect_gpus()
    temp = get_temperatures()

    print("=== Estado LUO-MAX ===")
    print(f"CPU: {cpu['model']} ({cpu['cores']} hilos)")
    govs = set()
    for gov_path in glob.glob(f"{CPU_ROOT}/cpu[0-9]*/cpufreq/scaling_governor"):
        govs.add(read_file(gov_path, "?"))
    print(f"Governor(es) activo(s): {', '.join(govs) if govs else 'no disponible (sin cpufreq)'}")
    if cpu["has_intel_pstate"]:
        no_turbo = read_file(f"{INTEL_PSTATE}/no_turbo")
        print(f"Intel Turbo Boost: {'ACTIVADO' if no_turbo == '0' else 'desactivado'}")
    print(f"GPU Intel: {'sí (' + str(len(gpus['intel_cards'])) + ')' if gpus['intel_cards'] else 'no'}")
    print(f"GPU AMD: {'sí (' + str(len(gpus['amd_cards'])) + ')' if gpus['amd_cards'] else 'no'}")
    print(f"GPU NVIDIA (nvidia-smi): {'sí (' + str(gpus['nvidia_count']) + ')' if gpus['nvidia'] else 'no'}")
    print(f"Temperatura máxima detectada: {f'{temp:.1f}°C' if temp else 'no disponible'}")
    power = detect_power_source()
    print(f"Alimentación: {power if power else 'sin batería (sobremesa/servidor) o no detectable'}")

    if os.path.exists(PID_FILE):
        pid = read_file(PID_FILE)
        running = pid and os.path.exists(f"/proc/{pid}")
        print(f"Demonio en background: {'ACTIVO (PID ' + pid + ')' if running else 'inactivo (pid obsoleto)'}")
    else:
        print("Demonio en background: inactivo")

    print(f"Backup disponible para 'restore': {'sí' if load_backup() else 'no'}")


# ------------------------------------------------------------------------
# Demonio (aplica una vez y luego vigila + limpia cada N segundos)
# ------------------------------------------------------------------------

_stop_requested = False


def _handle_signal(signum, frame):
    global _stop_requested
    _stop_requested = True


def run_daemon(extreme, interval, temp_limit, temp_recover, verbose, quiet):
    if not is_root():
        log("❌ El demonio necesita permisos de root (usa sudo).")
        sys.exit(1)

    ensure_state_dir()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cpu, gpus = apply_all(extreme=extreme, verbose=verbose, quiet=quiet)
    log(f"🌀 Demonio LUO-MAX iniciado. Limpiando caché/temporales cada "
        f"{interval // 60} min y vigilando temperatura (límite {temp_limit}°C).", quiet=quiet)

    throttled = False
    elapsed = 0
    tick = 10  # revisa temperatura cada 10s, limpia cada `interval`
    try:
        while not _stop_requested:
            time.sleep(tick)
            elapsed += tick

            throttled = thermal_guard(cpu, extreme, temp_limit, temp_recover, throttled, verbose)

            if elapsed >= interval:
                elapsed = 0
                if not quiet:
                    log(f"🧹 Ciclo de limpieza periódica ({datetime.now().strftime('%H:%M:%S')})", quiet=quiet)
                clean_cycle(verbose and not quiet)
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        log("🛑 Demonio LUO-MAX detenido.", quiet=quiet)


def stop_daemon():
    if not os.path.exists(PID_FILE):
        print("El demonio no está corriendo (no hay PID registrado).")
        return
    pid = read_file(PID_FILE)
    try:
        os.kill(int(pid), signal.SIGTERM)
        print(f"✓ Señal de parada enviada al demonio (PID {pid}).")
    except Exception as e:
        print(f"⚠ No se pudo detener el demonio: {e}")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)


# ------------------------------------------------------------------------
# Instalación como servicio systemd persistente
# ------------------------------------------------------------------------

def install_service(extreme, interval):
    if not is_root():
        print("❌ Necesitas root (sudo) para instalar el servicio.")
        sys.exit(1)

    script_path = os.path.abspath(__file__)
    run(["cp", script_path, BIN_INSTALL_PATH])
    run(["chmod", "+x", BIN_INSTALL_PATH])

    extra = " --extreme" if extreme else ""
    service_content = f"""[Unit]
Description=LUO-MAX Turbo/Overclock Daemon
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {BIN_INSTALL_PATH} daemon --interval {interval}{extra} --quiet
ExecStop=/usr/bin/python3 {BIN_INSTALL_PATH} stop
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    with open(SERVICE_PATH, "w") as f:
        f.write(service_content)

    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "luo-max.service"])
    run(["systemctl", "restart", "luo-max.service"])
    print(f"✅ Servicio 'luo-max' instalado y activo (arranca automáticamente con el sistema).")
    print(f"   Binario: {BIN_INSTALL_PATH}")
    print(f"   Unidad:  {SERVICE_PATH}")
    print("   Comandos útiles: systemctl status luo-max | journalctl -u luo-max -f")


def uninstall_service():
    if not is_root():
        print("❌ Necesitas root (sudo) para desinstalar el servicio.")
        sys.exit(1)

    run(["systemctl", "stop", "luo-max.service"])
    run(["systemctl", "disable", "luo-max.service"])
    if os.path.exists(SERVICE_PATH):
        os.remove(SERVICE_PATH)
    run(["systemctl", "daemon-reload"])

    restore_all(verbose=False)

    if os.path.exists(BIN_INSTALL_PATH):
        os.remove(BIN_INSTALL_PATH)
    if os.path.exists(SYSCTL_CONF):
        os.remove(SYSCTL_CONF)

    print("✅ Servicio 'luo-max' desinstalado y sistema restaurado a sus valores originales.")


# ------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LUO-MAX: lleva CPU/GPU al máximo rendimiento según el hardware y limpia el "
                    "sistema periódicamente (inspirado en GameMode, pero permanente).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_apply = sub.add_parser("apply", help="Aplica el perfil turbo una sola vez y termina.")
    p_apply.add_argument("--extreme", action="store_true",
                          help="Bloquea la CPU siempre a la frecuencia máxima (más calor/consumo).")
    p_apply.add_argument("--quiet", action="store_true")

    p_daemon = sub.add_parser("daemon", help="Aplica el perfil turbo y se queda vigilando/limpiando.")
    p_daemon.add_argument("--extreme", action="store_true")
    p_daemon.add_argument("--interval", type=int, default=DEFAULT_CLEAN_INTERVAL,
                           help=f"Segundos entre limpiezas (por defecto {DEFAULT_CLEAN_INTERVAL} = 5 min).")
    p_daemon.add_argument("--temp-limit", type=float, default=DEFAULT_TEMP_LIMIT_C,
                           help=f"°C a partir de los cuales se baja el rendimiento por seguridad "
                                f"(por defecto {DEFAULT_TEMP_LIMIT_C}).")
    p_daemon.add_argument("--temp-recover", type=float, default=DEFAULT_TEMP_RECOVER_C,
                           help=f"°C por debajo de los cuales se reactiva el turbo (por defecto {DEFAULT_TEMP_RECOVER_C}).")
    p_daemon.add_argument("--quiet", action="store_true")

    sub.add_parser("stop", help="Detiene el demonio en background.")
    sub.add_parser("status", help="Muestra el estado actual del sistema.")
    sub.add_parser("restore", help="Revierte todos los cambios a los valores originales.")

    p_install = sub.add_parser("install-service", help="Instala LUO-MAX como servicio systemd persistente.")
    p_install.add_argument("--extreme", action="store_true")
    p_install.add_argument("--interval", type=int, default=DEFAULT_CLEAN_INTERVAL)

    sub.add_parser("uninstall-service", help="Quita el servicio systemd y restaura el sistema.")

    args = parser.parse_args()

    if args.command == "apply":
        apply_all(extreme=args.extreme, verbose=True, quiet=args.quiet)
    elif args.command == "daemon":
        run_daemon(args.extreme, args.interval, args.temp_limit, args.temp_recover,
                   verbose=True, quiet=args.quiet)
    elif args.command == "stop":
        stop_daemon()
    elif args.command == "status":
        print_status()
    elif args.command == "restore":
        restore_all()
    elif args.command == "install-service":
        install_service(args.extreme, args.interval)
    elif args.command == "uninstall-service":
        uninstall_service()


if __name__ == "__main__":
    main()
