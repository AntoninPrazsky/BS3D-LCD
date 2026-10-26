"""The status strip along the top of every page (#5).

Left, the server's state: a slowly beating dot and ONLINE while all is well,
an icon when there are warnings or errors, OFFLINE inverted when the service
is down; after it an envelope while a note is unacknowledged (#8). In the middle the time, with a blinking colon that is also the
display's own heartbeat (#6). Right, a dot for each page.
"""

import math
import time

from PIL import Image

from .ui import GREY, WIDTH, draw_icon, page

HEIGHT = 9
BEAT = 2.4          # seconds per beat of the online dot

# A dotted rule under the strip.
RULE = Image.new("1", (WIDTH, 1))
RULE.putdata([255 if x % 2 == 0 else 0 for x in range(WIDTH)])


def status(ui, image, state, t):
    """The left part: the server's state. Returns its width."""
    font = ui.tiny
    server = state.server
    if server is None:
        return font.draw(image, 0, 1, "STARTING")
    if not server.online:
        width = font.width("OFFLINE") + 4
        image.paste(255, (0, 0, width, 8))
        font.draw(image, 2, 1, "OFFLINE", fill=0)
        return width
    if state.errors:
        x = draw_icon(image, 0, 1, "error") + 2
        return x + font.draw(image, x, 1, "ERROR")
    if state.warnings:
        x = draw_icon(image, 0, 1, "warning") + 2
        return x + font.draw(image, x, 1, str(len(state.warnings)))
    beat = (1 - math.cos(2 * math.pi * t / BEAT)) / 2
    x = draw_icon(image, 0, 1, "dot", fill=round(255 - (255 - GREY) * beat)) + 2
    return x + font.draw(image, x, 1, "ONLINE")


def clock(ui, image, wall, centre):
    """HH:MM with a colon that blinks once a second, centred on ``centre``. Returns its
    right edge."""
    font = ui.tiny
    local = time.localtime(wall)
    hours, minutes = f"{local.tm_hour:02d}", f"{local.tm_min:02d}"
    x = centre - font.width(f"{hours}:{minutes}") // 2
    x += font.draw(image, x, 1, hours) + 1
    if wall % 1.0 < 0.5:
        font.draw(image, x, 1, ":")
    x += font.width(":") + 1
    return x + font.draw(image, x, 1, minutes)


def dots(image, index, count, right, left=0):
    """A dot for each page, the current one dark; narrower dots when so many would
    reach ``left`` (eight pages and more, with the clock there)."""
    gap = 2
    for width in (4, 3, 2):
        if count * (width + gap) - gap <= right - left:
            break
    x = right - (count * (width + gap) - gap)
    for i in range(count):
        image.paste(255 if i == index else GREY, (x, 2, x + width, 5))
        x += width + gap


def render(ui, state, t, index=0, count=0, label=None):
    """The strip as a greyscale image, ``WIDTH`` x ``HEIGHT``; ``label`` replaces
    its contents."""
    image = page(WIDTH, HEIGHT)
    if label:
        # The compare tools: the setting on show, instead of everything else.
        ui.tiny.draw(image, WIDTH // 2, 1, label, align="center")
    else:
        x = status(ui, image, state, t)
        if state.unseen:
            draw_icon(image, x + 4, 1, "note")
        edge = clock(ui, image, state.now, WIDTH // 2 + 6)
        if count > 1:
            dots(image, index, count, WIDTH, edge + 2)
    image.paste(255, (0, HEIGHT - 1), RULE)
    return image
