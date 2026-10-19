"""Copy the X11 misc-fixed fonts the panel uses into bs3d_lcd/assets/fonts, cut to
the characters it draws.

The fonts are the public-domain "misc-fixed" family by Markus Kuhn and others
(https://gitlab.freedesktop.org/xorg/font/misc-misc). Every size covers every
letter a BS3D nickname may hold (U+0020 to U+017F); the subsets keep those and
a few symbols, and the files' own headers, copyright line included.

    python3 tools/subset_fonts.py PATH/TO/misc-misc
"""

import os
import sys

FONTS = ("5x8", "6x10", "6x13B", "7x13B", "9x15B", "10x20")

# The nickname alphabet and the rest of Latin-1, plus symbols the pages use.
KEEP = set(range(0x20, 0x7F)) | set(range(0xA0, 0x180)) | {
    0x2009,                          # thin space, between thousands
    0x2013, 0x2014, 0x2022, 0x2026,  # – — • …
    0x2190, 0x2191, 0x2192, 0x2193,  # ← ↑ → ↓
    0x2605, 0x2713, 0x2715, 0x26A0,  # ★ ✓ ✕ ⚠
    0x25B2, 0x25BC, 0x25CF, 0x25CB,  # ▲ ▼ ● ○
}

OUT = os.path.join(os.path.dirname(__file__), "..", "bs3d_lcd", "assets", "fonts")


def subset(src, dst):
    with open(src, encoding="latin-1") as f:
        lines = f.read().splitlines()
    head = lines[:next(i for i, line in enumerate(lines) if line.startswith("CHARS "))]
    chars, glyph, code = [], [], None
    for line in lines[len(head) + 1:]:
        if line.startswith("STARTCHAR"):
            glyph, code = [line], None
        elif glyph:
            glyph.append(line)
            if line.startswith("ENCODING "):
                code = int(line.split()[1])
            elif line == "ENDCHAR":
                if code in KEEP:
                    chars.append(glyph)
                glyph = []
    with open(dst, "w", encoding="latin-1", newline="\n") as f:
        f.write("\n".join(head) + "\n")
        f.write(f"COMMENT Subset for BS3D-LCD by tools/subset_fonts.py: U+0020-U+017F and "
                f"a few symbols\n")
        f.write(f"CHARS {len(chars)}\n")
        for glyph in chars:
            f.write("\n".join(glyph) + "\n")
        f.write("ENDFONT\n")
    return len(chars)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    os.makedirs(OUT, exist_ok=True)
    for name in FONTS:
        n = subset(os.path.join(argv[1], f"{name}.bdf"), os.path.join(OUT, f"{name}.bdf"))
        print(f"{name}.bdf: {n} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
