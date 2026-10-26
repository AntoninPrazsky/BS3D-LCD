"""The newest note acknowledged (#8), kept in a file so that a restart or a reboot does
not ring again for notes already seen."""

import os

NAME = "notes-seen"


def path_from_environment(environ=os.environ):
    """``$STATE_DIRECTORY/notes-seen`` under systemd (the unit's ``StateDirectory=``),
    else None: kept in memory only."""
    directory = environ.get("STATE_DIRECTORY")
    return os.path.join(directory.split(":")[0], NAME) if directory else None


class Seen:
    """``at``: when the newest note acknowledged came (Unix seconds), or None until the
    first snapshot that lists notes.

    Notes are told apart by when they came, never by their id: BS3D-API's
    ``notes.id`` has no ``AUTOINCREMENT``, so a note may take a deleted one's id.
    A file that cannot be read counts as none; one that cannot be written is
    logged, and the moment is kept in memory.
    """

    def __init__(self, path=None, at=None, log=None):
        self.path, self.log = path, log
        self.at = at if at is not None else self._load()

    def _say(self, line):
        if self.log:
            self.log(line)

    def _load(self):
        if not self.path:
            return None
        try:
            with open(self.path, encoding="ascii") as f:
                return float(f.read().strip())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            self._say(f"{self.path}: {e}; the notes there now count as seen")
            return None

    def set(self, at):
        if at == self.at:
            return
        self.at = at
        if not self.path:
            return
        temporary = self.path + ".tmp"
        try:
            with open(temporary, "w", encoding="ascii") as f:
                f.write(f"{at!r}\n")
            os.replace(temporary, self.path)
        except OSError as e:
            self._say(f"{self.path}: {e}")
