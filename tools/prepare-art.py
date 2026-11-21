"""Turn the full-body expression sheets (expr/mio_*.png, 1664x2496 RGBA) into
web assets for the stage.

  python3 tools/prepare-art.py path/to/expr

Writes art/<name>.webp (upper body, source pixels 0..1664 x 0..1560, scaled to
1280 px wide) plus feathered overlay patches cut from the same sheets:

  art/blink-l.webp, art/blink-r.webp  eyes from the "closed" sheet (blinking, winking)
  art/mouth-open.webp                 the small open mouth from the "surprise" sheet (lip sync)

All sheets share one pose, so a patch lines up when drawn at its source box.
Boxes are in source-pixel coordinates; the page draws everything in that space.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "art"
CROP = (0, 0, 1664, 1560)          # upper body; legs and bag are off stage
SCALE = 1280 / 1664
NAMES = {
    "mio_01_smile_01": "smile", "mio_02_laugh_01": "laugh", "mio_03_shy_01": "shy",
    "mio_04_surprise_01": "surprise", "mio_05_pout_01": "pout", "mio_06_sad_01": "sad",
    "mio_07_think_01": "think", "mio_08_closed_01": "closed",
}
PATCHES = {  # name: (source sheet, box x0, y0, x1, y1)
    "blink-l": ("closed", (690, 322, 832, 448)),
    "blink-r": ("closed", (858, 316, 1002, 442)),
    "mouth-open": ("surprise", (782, 448, 908, 530)),
}


def feathered(img: Image.Image, feather: int) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((feather, feather, w - feather, h - feather), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather / 2))
    out = img.copy()
    out.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (w, h), 0), mask))
    return out


def main(src: Path):
    OUT.mkdir(exist_ok=True)
    sheets = {}
    for f in sorted(src.glob("mio_*.png")):
        key = NAMES.get(f.stem)
        if not key:
            continue
        im = Image.open(f).convert("RGBA")
        sheets[key] = im
        base = im.crop(CROP)
        base = base.resize((round(base.width * SCALE), round(base.height * SCALE)), Image.LANCZOS)
        base.save(OUT / f"{key}.webp", "WEBP", quality=84, method=6)
    meta = {"size": [CROP[2] - CROP[0], CROP[3] - CROP[1]], "patches": {}}
    for name, (sheet, box) in PATCHES.items():
        patch = feathered(sheets[sheet].crop(box), feather=14)
        patch.save(OUT / f"{name}.webp", "WEBP", quality=90, method=6)
        meta["patches"][name] = list(box)
    (OUT / "art.json").write_text(json.dumps(meta), encoding="utf-8")
    for p in sorted(OUT.glob("*.webp")):
        print(f"{p.name:18} {p.stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
