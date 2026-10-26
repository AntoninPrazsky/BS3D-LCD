"""The status snapshot BS3D-API writes for the panel (BS3D-API#13).

``bs3d-api-status.service`` rewrites ``/run/bs3d-status/status.json`` every
15 s: counts, today's play, the newest clears and since BS3D-API#15 the newest
submissions and the players who played last, the Top players and the backup
records, never a hash or a hidden player. A key a service before #15 does not
write is read as empty. The display's user reads it as a
member of the group ``bs3d-status``; it never reads the database itself.
"""

import json
from datetime import datetime

from .state import Clear, Play, Player, RecentPlayer

FORMAT = 1


def read(path):
    """The snapshot as a dict; raises if it is missing, unreadable or of another format."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != FORMAT:
        raise ValueError(f"format {data.get('format')!r}, not {FORMAT}")
    return data


def moment(text):
    """A moment as the snapshot writes it (ISO 8601, .NET's seven decimals) as Unix seconds."""
    return datetime.fromisoformat(text).timestamp() if text else None


def clears(rows):
    return tuple(Clear(c["level"], c["player"], c["stars"], c["score"], moment(c["at"])) for c in rows)


def players(rows):
    return tuple(Player(r["rank"], r["name"], r["score"], r["levels"], r["stars"]) for r in rows)


def play(data):
    """The ``Play`` part of the state."""
    today, totals, top = data["today"], data["totals"], data["top"]
    return Play(
        at=moment(data["written_at"]),
        hours=tuple(data["hours"]),
        clears_today=today["clears"],
        attempts_today=today["attempts"],
        players_today=today["active_players"],
        new_players_today=today["new_players"],
        seconds_today=today["seconds_played"],
        last_score_at=moment(data.get("last_submission_at")),
        latest=clears(data["latest"]),
        recent=clears(data.get("recent") or ()),
        recent_players=tuple(RecentPlayer(r["player"], moment(r["last_at"]), r["clears"], r["attempts"],
                                          r["first_day"]) for r in data.get("recent_players") or ()),
        month=top["month"],
        top_month=players(top["this_month"]),
        top_all=players(top["all_time"]),
        players=totals["players"],
        clears=totals["clears"],
        attempts=totals["attempts"],
        boards=totals["boards"],
        boards_cleared=totals["boards_with_clear"],
        notes=totals["notes"],
    )


def backups(data):
    """{"offbox": (result, attempt, ok, every), "offsite": ...} for the copies set up."""
    out = {}
    for name, record in (data.get("backups") or {}).items():
        if record:
            out[name] = (record["result"], moment(record.get("attempt")), moment(record.get("ok")),
                         record.get("every") or 1)
    return out
