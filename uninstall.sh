#!/bin/bash

if [ "$EUID" -ne 0 ]; then
  echo "❌ Por favor, ejecuta este script con sudo: sudo ./uninstall.sh"
  exit 1
fi

echo "🗑️ Desinstalando Linux Universal Optimizer..."

# Deshabilitar y borrar el servicio systemd
systemctl disable luo.service 2>/dev/null
rm -f /etc/systemd/system/luo.service
systemctl daemon-reload

# Borrar archivos instalados
rm -rf /usr/local/share/luo
rm -f /usr/local/bin/luo
rm -f /etc/sysctl.d/99-luo-performance.conf

echo "✅ LUO ha sido completamente removido del sistema."
