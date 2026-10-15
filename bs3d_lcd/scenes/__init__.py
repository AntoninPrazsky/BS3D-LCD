"""The scenes, by name.

A scene factory takes the ``Panel`` and keyword options (``duration``,
``fps``, ``blink``, ``now``; each takes what it needs) and returns a
``Scene``.
"""

from .gallery import bubbles, circles, gradient, planet, sphere
from .logo import logo
from .test import test

SCENES = {
    "logo": logo,
    "test": test,
    "gradient": gradient,
    "sphere": sphere,
    "circles": circles,
    "planet": planet,
    "bubbles": bubbles,
}


def build(names, panel, **options):
    return [SCENES[name](panel, **options) for name in names]
