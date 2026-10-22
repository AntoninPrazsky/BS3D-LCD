#!/bin/bash
# Remove the BS3D-LCD service, its code and its user; /etc/bs3d-lcd stays.
#
#   sudo deploy/uninstall.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run it as root: sudo $0" >&2
    exit 1
fi

systemctl disable --now --quiet bs3d-lcd 2>/dev/null || true
rm -f /etc/systemd/system/bs3d-lcd.service
systemctl daemon-reload
rm -rf /opt/bs3d-lcd
if id bs3d-lcd >/dev/null 2>&1; then
    userdel bs3d-lcd
fi
echo "Removed the bs3d-lcd service, /opt/bs3d-lcd and the user; /etc/bs3d-lcd is kept."
