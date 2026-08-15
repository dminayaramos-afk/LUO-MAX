#!/bin/bash

# Verificar permisos de superusuario
if [ "$EUID" -ne 0 ]; then
  echo "❌ Por favor, ejecuta este script con sudo: sudo ./install.sh"
  exit 1
fi

echo "🚀 Instalando Linux Universal Optimizer (LUO)..."

# Crear directorios de destino
mkdir -p /usr/local/share/luo
mkdir -p /etc/luo

# Copiar todo el código fuente al directorio del sistema
cp -r core detection backup optimization gaming persistence /usr/local/share/luo/
cp luo /usr/local/bin/luo
chmod +x /usr/local/bin/luo

# Crear servicio systemd para persistencia permanente
cat << 'SERVICE' > /etc/systemd/system/luo.service
[Unit]
Description=Linux Universal Optimizer Permanent Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/luo optimize --auto
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE

# Habilitar y arrancar el servicio systemd
systemctl daemon-reload
systemctl enable luo.service

echo "✅ ¡Instalación completada! LUO ahora es permanente en el sistema hasta que lo desinstales."
