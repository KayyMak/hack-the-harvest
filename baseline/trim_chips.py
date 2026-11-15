"""Trim the white margins around the before/after chip images (display only; no pixels of the picture change).

The chips are rendered as 320x320 squares, so wide or tall fields leave white bands around the satellite picture.
This crops each PNG to the box holding its non-white pixels (the picture plus its date/NDVI title), with a 2 px
margin, in baseline/outputs/chips/ and the static snapshot copy web/public/snapshot/chips/. Idempotent.

    python baseline/trim_chips.py
"""
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
DIRS = [ROOT / 'baseline' / 'outputs' / 'chips', ROOT / 'web' / 'public' / 'snapshot' / 'chips']
PAD = 2


def trim(path: Path) -> bool:
    im = Image.open(path)
    rgb = im.convert('RGB')
    white = Image.new('RGB', rgb.size, (255, 255, 255))
    # pixels that differ from white by more than a faint anti-aliasing tint
    diff = ImageChops.difference(rgb, white).convert('L').point(lambda v: 255 if v > 24 else 0)
    box = diff.getbbox()
    if not box:
        return False
    l, t, r, b = box
    box = (max(0, l - PAD), max(0, t - PAD), min(rgb.width, r + PAD), min(rgb.height, b + PAD))
    if box == (0, 0, rgb.width, rgb.height):
        return False
    im.crop(box).save(path, optimize=True)
    return True


if __name__ == '__main__':
    for d in DIRS:
        files = sorted(d.glob('*.png'))
        changed = sum(trim(p) for p in files)
        print(f'{d.relative_to(ROOT)}: {changed} of {len(files)} trimmed')
