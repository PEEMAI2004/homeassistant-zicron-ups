#!/bin/bash
set -e

echo "[INFO] Starting Zicron UPS Add-on initialization..."

# Prepare state directories
mkdir -p /etc/nut /var/run/nut /var/lib/nut /run/nut
chown -R root:nut /var/run/nut /var/lib/nut /run/nut /etc/nut 2>/dev/null || true
chmod 775 /var/run/nut /var/lib/nut /run/nut 2>/dev/null || true

# Generate NUT configuration
cat << 'EOF' > /etc/nut/nut.conf
MODE=netserver
EOF

cat << 'EOF' > /etc/nut/ups.conf
pollinterval = 2
maxretry = 3

[zicron]
    driver = dummy-ups
    port = /etc/nut/zicron.dev
    desc = "Zicron UPS"
EOF

cat << 'EOF' > /etc/nut/upsd.conf
LISTEN 0.0.0.0 3493
LISTEN 127.0.0.1 3493
LISTEN :: 3493
EOF

cat << 'EOF' > /etc/nut/upsd.users
[ha]
    password = homeassistant
    actions = SET
    instcmds = ALL
    upsmon master
EOF

# Initial baseline device file
if [ ! -f /etc/nut/zicron.dev ]; then
cat << 'EOF' > /etc/nut/zicron.dev
device.mfr: Zicron
device.model: UPSmart-HID
device.type: ups
battery.charge: 100
battery.voltage: 13.7
battery.voltage.nominal: 12.0
input.voltage: 230.0
input.voltage.fault: 0.0
output.voltage: 230.0
output.frequency: 50.0
ups.load: 0
ups.temperature: 25.0
ups.status: OL
EOF
fi

chmod 644 /etc/nut/* 2>/dev/null || true

# Locate driver and daemon binaries
DRV_PATH=$(which dummy-ups 2>/dev/null || ls /lib/nut/dummy-ups /usr/lib/nut/dummy-ups 2>/dev/null | head -n 1)
UPSD_PATH=$(which upsd 2>/dev/null || ls /lib/nut/upsd /usr/lib/nut/upsd /usr/sbin/upsd 2>/dev/null | head -n 1)

echo "[INFO] Starting NUT driver ($DRV_PATH)..."
$DRV_PATH -a zicron -B -u root 2>/dev/null || true

echo "[INFO] Starting NUT server ($UPSD_PATH)..."
$UPSD_PATH -B -u root 2>/dev/null || true

echo "[INFO] Starting Zicron UPS Telemetry Daemon..."
exec python3 /app/zicron_ups_daemon.py
