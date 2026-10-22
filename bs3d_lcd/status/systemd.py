"""Telling systemd how the service is doing (#6): sd_notify without a library.

``notify("READY=1")`` once the panel shows something, ``WATCHDOG=1`` from the
render loop, ``STATUS=...`` for ``systemctl status``. Without a
``NOTIFY_SOCKET`` (a manual run) it does nothing.
"""

import os
import socket


def notify(message):
    """Send one message to systemd; False if there is no one to tell."""
    address = os.environ.get("NOTIFY_SOCKET")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]       # an abstract socket
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(message.encode(), address)
        except OSError:
            return False
    return True


def watchdog_interval():
    """How often systemd wants to hear the watchdog, in s; None if it does not."""
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec or os.environ.get("WATCHDOG_PID", str(os.getpid())) != str(os.getpid()):
        return None
    return int(usec) / 1e6
