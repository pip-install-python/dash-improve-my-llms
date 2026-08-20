"""The llms mark, take two: a hook through the document.

Layer order is the trick — eye+shank BEHIND the page, bend+point IN FRONT —
so the hook visibly passes through the sheet: in behind the top edge, a U
below the bottom edge, and the point piercing back up in front of the page.
"""
from PIL import Image, ImageDraw, ImageFilter
import sys

S = 4
W = 512 * S

BG_TOP = (149, 115, 249, 255)
BG_BOT = (105, 67, 218, 255)
PAGE = (255, 255, 255, 255)
LINE = (95, 53, 216, 255)
HOOK = (43, 26, 100, 255)

def sc(*vals):
    return [v * S for v in vals]

def rounded_line(d, x0, y0, x1, y1, w, fill):
    d.line(sc(x0, y0, x1, y1), fill=fill, width=w * S)
    r = w * S // 2
    for (x, y) in ((x0, y0), (x1, y1)):
        d.ellipse([x * S - r, y * S - r, x * S + r, y * S + r], fill=fill)

grad = Image.new("RGBA", (W, W))
for y in range(W):
    t = y / (W - 1)
    row = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT))
    grad.paste(row, (0, y, W, y + 1))
mask = Image.new("L", (W, W), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=110 * S, fill=255)
img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)

# geometry
PX0, PY0, PX1, PY1 = 112, 116, 358, 360      # the page
SHX = 330                                     # shank x
RISEX = 214                                   # point-side x
BENDY = 385                                   # bend center y (below the page)
BENDC = (SHX + RISEX) // 2                    # 272
BENDR = (SHX - RISEX) // 2                    # 58
HW = 34

# 1 — BEHIND the page: eye + shank
er = 31
d.ellipse(sc(SHX - er, 76 - er, SHX + er, 76 + er), outline=HOOK, width=17 * S)
rounded_line(d, SHX, 96, SHX, BENDY, HW, HOOK)

# 2 — the page
sh = Image.new("RGBA", (W, W), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle(sc(PX0, PY0 + 7, PX1, PY1 + 7), radius=30 * S,
                                     fill=(30, 10, 80, 90))
img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6 * S)))
d = ImageDraw.Draw(img)
d.rounded_rectangle(sc(PX0, PY0, PX1, PY1), radius=30 * S, fill=PAGE)
# rows 2-3 stop short of the hook's lane — the text makes way for the
# thing passing through it, which is most of the joke.
for y, x1 in ((172, 284), (226, 186), (280, 186)):
    rounded_line(d, 148, y, x1, y, 26, LINE)

# 3 — IN FRONT: bend, rise, tip, barb
d.arc(sc(BENDC - BENDR, BENDY - BENDR, BENDC + BENDR, BENDY + BENDR),
      start=0, end=180, fill=HOOK, width=HW * S)
d.line(sc(RISEX, BENDY, RISEX, 282), fill=HOOK, width=HW * S)  # no top cap:
r = HW * S // 2                                                  # the tip's base
d.ellipse([RISEX * S - r, BENDY * S - r, RISEX * S + r, BENDY * S + r], fill=HOOK)
# the point: a sharp claw leaning slightly back toward the shank
d.polygon(sc(RISEX - 17, 286, RISEX + 17, 286, RISEX + 10, 214), fill=HOOK)
# the barb: a small tight triangle jutting down-left below the point
d.polygon(sc(RISEX - 17, 298, RISEX - 42, 322, RISEX - 17, 334), fill=HOOK)

img = img.resize((512, 512), Image.LANCZOS)
img.save(sys.argv[1])
print("wrote", sys.argv[1])
