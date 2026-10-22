#!/bin/bash
# Install or update the BS3D-LCD status display as a system service (#6).
#
#   sudo deploy/install.sh
#
# - The code goes to /opt/bs3d-lcd, in its own venv, from this checkout.
# - The service runs as the system user bs3d-lcd: no home, no login, and only
#   the groups the unit names (spi, gpio, video, systemd-journal), plus
#   bs3d-status, which reads BS3D-API's status snapshot, when that exists.
# - The settings are /etc/bs3d-lcd/config.toml. The first install makes it
#   from your ~/.config/bs3d-lcd/config.toml, or from the example; later
#   installs leave it alone.
# - Then the bs3d-lcd service is enabled and (re)started.
#
# To update: git pull, then run it again.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run it as root: sudo $0" >&2
    exit 1
fi

SRC=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=/opt/bs3d-lcd
NAME=bs3d-lcd

if ! id "$NAME" >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$NAME"
    echo "Added the system user $NAME."
fi
# BS3D-API's status snapshot, the play statistics (its #13), is for the group bs3d-status, which its
# deploy/install-status.sh adds. The restart below picks the membership up.
if getent group bs3d-status >/dev/null; then
    usermod -a -G bs3d-status "$NAME"
fi

# Build from a copy, so that nothing in the checkout ends up owned by root.
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
tar -C "$SRC" --exclude=.git --exclude=.venv --exclude=build --exclude='*.egg-info' \
    --exclude=__pycache__ -cf - . | tar -C "$build" -xf -

install -d -m 755 "$PREFIX"
if [ ! -x "$PREFIX/venv/bin/python" ]; then
    python3 -m venv "$PREFIX/venv"
fi
"$PREFIX/venv/bin/pip" install --quiet --disable-pip-version-check "$build"
"$PREFIX/venv/bin/pip" install --quiet --disable-pip-version-check --no-deps --force-reinstall "$build"
git -c safe.directory="$SRC" -C "$SRC" describe --always --dirty > "$PREFIX/COMMIT" 2>/dev/null || true
echo "Installed $(cat "$PREFIX/COMMIT" 2>/dev/null || echo "the checkout") into $PREFIX."

install -d -m 755 /etc/bs3d-lcd
if [ ! -e /etc/bs3d-lcd/config.toml ]; then
    home=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
    if [ -n "${SUDO_USER:-}" ] && [ -f "$home/.config/bs3d-lcd/config.toml" ]; then
        install -m 644 "$home/.config/bs3d-lcd/config.toml" /etc/bs3d-lcd/config.toml
        echo "Settings: /etc/bs3d-lcd/config.toml, from $home/.config/bs3d-lcd/config.toml."
    else
        install -m 644 "$SRC/deploy/config.example.toml" /etc/bs3d-lcd/config.toml
        echo "Settings: /etc/bs3d-lcd/config.toml, from the example."
    fi
fi

install -m 644 "$SRC/deploy/bs3d-lcd.service" /etc/systemd/system/bs3d-lcd.service
systemctl daemon-reload
systemctl enable --quiet "$NAME"
systemctl restart "$NAME"
sleep 3
systemctl --no-pager --lines=8 status "$NAME" || true
