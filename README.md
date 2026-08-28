# LUO-MAX — Linux Universal Optimizer (modo Turbo/Overclock)

Versión de **archivo único** de mi proyecto `linux-uniopti`, inspirada en el
funcionamiento de [GameMode](https://github.com/FeralInteractive/gamemode):
en vez de activar el máximo rendimiento solo mientras corre un juego, lo
mantiene **siempre activo**, adaptado al hardware que detecte, y de forma
periódica libera RAM y borra temporales para que el sistema no se degrade.

Todo el código vive en **`luo-max.py`** — un único archivo Python 3, sin
dependencias externas.

## Universal: se adapta a CUALQUIER dispositivo

Igual que GameMode no asume una GPU o CPU concreta, `luo-max` detecta en
cada equipo qué hay realmente disponible y solo toca lo que existe —
funciona en:

- **CPU**: Intel (con o sin `intel_pstate`), AMD (boost de `acpi-cpufreq`),
  ARM (Raspberry Pi, mini-PCs, portátiles ARM) — el ajuste de *governor* y
  frecuencia máxima usa las rutas estándar del kernel, válidas en
  cualquier arquitectura con `cpufreq`.
- **GPU**: Intel integrada, AMD (`amdgpu`, integrada o dedicada), NVIDIA
  (una o varias, vía `nvidia-smi`) — o ninguna (servidores, VMs): en ese
  caso simplemente omite esa parte sin fallar.
- **Almacenamiento**: SSD/NVMe y HDD, detectados automáticamente vía
  `lsblk`, con el *scheduler* de E/S adecuado a cada tipo.
- **Alimentación**: si detecta batería (portátiles) avisa cuando estás
  usando el modo turbo sin estar conectado a corriente; en equipos de
  sobremesa/servidor sin batería simplemente lo omite.
- **Temperatura**: usa `/sys/class/thermal`, presente en la gran mayoría
  de equipos Linux modernos, independientemente del fabricante.

Si algo no está disponible en tu hardware concreto (por ejemplo, un
sobremesa sin `intel_pstate` ni GPU dedicada), el script lo detecta y
simplemente no aplica ese paso — nunca falla por ausencia de una pieza de
hardware.

## ¿Qué hace exactamente?

**CPU**
- Pone el *governor* de todos los núcleos en `performance`.
- Si es Intel (como tu i7-4500U): activa Turbo Boost (`no_turbo=0`) y sube
  `max_perf_pct` al 100%.
- Si el kernel expone `cpufreq/boost` (AMD/genérico): lo activa.
- Sube `scaling_max_freq` al máximo físico que soporta cada núcleo.
- Si tienes `cpupower` o `x86_energy_perf_policy` instalados, ajusta también
  la política energética a rendimiento.

**GPU** (aplica lo que exista, cero suposiciones)
- GPU Intel integrada: fija `gt_min_freq_mhz = gt_max_freq_mhz` para que
  nunca baje de la frecuencia máxima soportada.
- GPU AMD (`amdgpu`, integrada o dedicada): fuerza
  `power_dpm_force_performance_level=high` y selecciona el estado más alto
  disponible de reloj de núcleo/memoria (`pp_dpm_sclk`/`pp_dpm_mclk`).
- GPU(s) NVIDIA dedicada(s) — soporta más de una tarjeta —: activa
  *persistence mode* y sube el límite de potencia al máximo que reporte
  `nvidia-smi` en cada una. **Nota:** en GPUs móviles Kepler antiguas
  (como el 610M/710M/810M/820M de setups Optimus más viejos), el driver a
  veces no expone control de power limit — el script lo detecta y avisa
  en vez de fallar.

**Disco**
- `fstrim` en SSD/NVMe.
- Ajusta el *scheduler* de E/S (`none`/`mq-deadline` en SSD, `bfq` en HDD).

**Memoria y red**
- `vm.swappiness=1`, `vm.vfs_cache_pressure=50`, colas de red `fq` + `bbr`.

**Limpieza periódica (cada 5 min por defecto)**
- Libera caché de RAM (`drop_caches`).
- Borra archivos de `/tmp` y `/var/tmp` — pero **solo los que tengan más de
  5 minutos**, para no borrar algo que un programa esté usando en ese
  instante.

**Protección térmica (esto es lo que lo hace seguro para un portátil)**
- Vigila `/sys/class/thermal/thermal_zone*` cada 10 segundos mientras el
  demonio corre.
- Si la temperatura supera el límite (85°C por defecto), baja
  automáticamente a `powersave`/Turbo apagado hasta que se enfríe (75°C),
  y luego vuelve solo al modo turbo. Así evitas que un i7-4500U con años
  de uso y pasta térmica desgastada se sobrecaliente.

**Backup/Restore**
- Antes de tocar nada, guarda el estado original en
  `/var/lib/luo-max/backup.json`.
- `luo-max restore` revierte absolutamente todo (governors, turbo, sysctl,
  frecuencias de GPU) a como estaba antes.

## Instalación

```bash
sudo ./install.sh
```

Esto copia `luo-max.py` a `/usr/local/bin/luo-max`.

### Uso puntual (una sola vez, no permanente)

```bash
sudo luo-max apply
sudo luo-max status
sudo luo-max restore
```

### Uso permanente (recomendado — como pedías, "que se borre cada 5 min")

Instala el servicio systemd: arranca con el sistema, aplica el perfil turbo,
vigila temperatura y limpia cada 5 minutos en segundo plano:

```bash
sudo luo-max install-service
```

Comprobar que está corriendo:

```bash
systemctl status luo-max
journalctl -u luo-max -f
```

Modo extremo (bloquea siempre la CPU a máxima frecuencia — más rendimiento
constante pero más calor y batería; en un i7-4500U de 2014 úsalo con
cuidado, sobre todo si el portátil está sobre las piernas o mal ventilado):

```bash
sudo luo-max install-service --extreme
```

Cambiar el intervalo de limpieza (en segundos; 600 = 10 min):

```bash
sudo luo-max install-service --interval 600
```

### Desinstalar

```bash
sudo ./uninstall.sh
```

Detiene y borra el servicio, y **restaura automáticamente** los valores
originales del sistema (no deja el equipo "enganchado" a rendimiento máximo).

## Comandos disponibles

| Comando                  | Qué hace |
|---------------------------|----------|
| `apply [--extreme]`       | Aplica el perfil turbo una vez y termina |
| `daemon [--interval N]`   | Aplica + vigila temperatura + limpia cada N seg (foreground) |
| `stop`                    | Detiene el demonio en background |
| `status`                  | Muestra governor, turbo, GPU, temperatura, si el demonio corre |
| `restore`                 | Revierte todo a los valores originales |
| `install-service`         | Instala como servicio systemd persistente |
| `uninstall-service`       | Quita el servicio y restaura el sistema |

## Nota sobre tu equipo (Asus X550LC, i7-4500U, Optimus, MX Linux)

- El "overclock" real de CPU (subir el multiplicador más allá de fábrica)
  no es posible por software en un portátil con BIOS de fabricante bloqueada
  — lo que hace este script es **exprimir el 100% del rendimiento que Intel
  ya permite** (Turbo Boost, sin límites artificiales de gobernador de
  energía), que es lo máximo realista y seguro en este hardware.
- Con Optimus (Intel + NVIDIA GT6xx/7xx/8xx), si usas la NVIDIA solo para
  Roblox/Sober vía `prime-run` o similar, el ajuste de GPU Intel es el que
  más notarás en el día a día; el de NVIDIA se aplicará igual cuando la
  dedicada esté activa.
- Recomendación honesta: en un portátil de esta antigüedad, deja el modo
  `--extreme` desactivado salvo que necesites el máximo rendimiento un rato
  puntual — el modo normal ya activa Turbo Boost al 100% y solo evita que
  el CPU se quede "perezoso" en frecuencias bajas.
