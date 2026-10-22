"""The display's settings: where it reads the server, and the thresholds (#4).

They come from a TOML file: ``--config PATH``, else the first of
``/etc/bs3d-lcd/config.toml`` and ``~/.config/bs3d-lcd/config.toml`` that
exists. Everything has a default except the public address of the health
check through Cloudflare, which stays out of the repository; without it the
end-to-end check is left out.

    [sources]
    public_health = "https://scores.example.com/v1/health"

    [thresholds]
    temp_warning = 80
"""

import os
import tomllib
from dataclasses import dataclass, fields

PATHS = ("/etc/bs3d-lcd/config.toml", "~/.config/bs3d-lcd/config.toml")


@dataclass
class Config:
    # [sources]
    service: str = "bs3d-api"                       # the score service's unit
    tunnel: str = "cloudflared"                     # the tunnel's unit
    backup: str = "bs3d-api-backup"                 # the nightly backup's unit (and .timer)
    health: str = "http://127.0.0.1:5000/v1/health"
    ready: str = "http://127.0.0.1:20241/ready"     # cloudflared's readiness
    public_health: str | None = None                # the same health through Cloudflare
    release: str = "/opt/bs3d-api/current"          # a link to the running release
    backup_mount: str = "/mnt/bs3d-backup"
    snapshot: str = "/run/bs3d-status/status.json"  # BS3D-API's status snapshot (#13)

    # [thresholds]
    service_hold: float = 20.0          # s down before it alerts: a deploy's restart does not
    health_fails: int = 3               # failed checks in a row
    tunnel_hold: float = 60.0
    public_fails: int = 3
    temp_warning: float = 80.0          # °C, held 60 s
    temp_error: float = 85.0
    free_warning: float = 10.0          # % free on the disk or the card
    free_error: float = 3.0
    backup_age: float = 26.0            # hours since the last nightly backup
    log_window: float = 15.0            # minutes a logged error or warning stands
    snapshot_age: float = 120.0         # s: an older status snapshot is stale
    refusals_hour: int = 30             # refusals in an hour that are too many

    SECTIONS = {"sources": ("service", "tunnel", "backup", "health", "ready", "public_health",
                            "release", "backup_mount", "snapshot")}


def find(path=None):
    """The config file to read, or None for the defaults."""
    if path:
        return path
    for candidate in PATHS:
        candidate = os.path.expanduser(candidate)
        if os.path.exists(candidate):
            return candidate
    return None


def load(path=None):
    """The settings from ``path`` (or the usual places), over the defaults."""
    config = Config()
    path = find(path)
    if path is None:
        return config
    with open(path, "rb") as f:
        data = tomllib.load(f)
    names = {f.name for f in fields(Config)}
    sources = set(Config.SECTIONS["sources"])
    for section, values in data.items():
        if section not in ("sources", "thresholds") or not isinstance(values, dict):
            raise ValueError(f"{path}: unknown section [{section}]")
        for key, value in values.items():
            if key not in names or (key in sources) != (section == "sources"):
                raise ValueError(f"{path}: unknown setting {key} in [{section}]")
            setattr(config, key, value)
    return config
