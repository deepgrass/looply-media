"""Looply CG slow change: build the 33s video (3s previous CG answer intro + 30s question) in the live
make_puzzle.py layout from cg_render.py output, and keep the CG answer chain.
  python3 cg_video.py WORKDIR OUT.mp4 --state ~/Looply/output/auto/cg_state.json --music M.m4a [--dry-run]
WORKDIR has A.png, B.png, meta.json (cg_render.py). Writes OUT.mp4, OUT_answer_a/_b.png (ringed before/after),
OUT_sheet.jpg and OUT.json (meta + intro_from). The state file is NOT changed by a render: after the post
succeeded, record it with
  python3 cg_video.py --commit OUT.json --state ~/Looply/output/auto/cg_state.json [--media-id ID]
The intro shows the last committed entry of the state file (none -> 30s video without intro)."""
import argparse, datetime, glob, json, os, random, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H, FPS = 1080, 1920, 30
VW, VH = 1000, 900
PX, PY = (W - VW) // 2, 450
INTRO, CH_T, HOOK_T = 3.0, 30.0, 1.0
ACC = (255, 196, 90)
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"  # same font as the live videos on the Mac
FONTS = {"heavy": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "demi": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"}

ap = argparse.ArgumentParser()
ap.add_argument("work", nargs="?"); ap.add_argument("out", nargs="?"); ap.add_argument("--state", required=True)
ap.add_argument("--music"); ap.add_argument("--hook"); ap.add_argument("--commit"); ap.add_argument("--media-id")
ap.add_argument("--today", help="YYYY-MM-DD posting date (pre-rendering); default today")
ap.add_argument("--bg", default="216,232,246,248,226,214")  # backdrop gradient for transparent renders (top rgb, bottom rgb)
ap.add_argument("--sat", type=float, default=1.12)
a = ap.parse_args()
TODAY = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
STATE = json.load(open(a.state)) if os.path.exists(a.state) else {"history": []}
if a.commit:
    e = json.load(open(a.commit)); e["date"] = str(TODAY)
    if a.media_id:
        e["media_id"] = a.media_id
    STATE["history"].append(e)
    json.dump(STATE, open(a.state + ".tmp", "w"), indent=1); os.replace(a.state + ".tmp", a.state)
    print("recorded", e["answer"]); raise SystemExit(0)
OUT = a.out
META = json.load(open(os.path.join(a.work, "meta.json")))
PREV = STATE["history"][-1] if STATE["history"] else None
if PREV and not (os.path.exists(PREV["ans_a"]) and os.path.exists(PREV["ans_b"])):
    PREV = None
HOOK = a.hook or random.choice(["dontblink", "keepeyes"])


def FA(size, wt="heavy"):
    try:
        return ImageFont.truetype(AVENIR, size, index={"heavy": 8, "demi": 2}[wt])
    except Exception:
        return ImageFont.truetype(FONTS[wt], size)


def C(c):
    return np.array(c, np.float32)


def _s2lin(x):
    x = x / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _lin2s(x):
    x = np.clip(x, 0, 1)
    return 255.0 * np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def _ease(x):
    x = min(max(x, 0.0), 1.0); e = 0.08; vmax = 1 / (1 - e)
    if x < e:
        return vmax * x * x / (2 * e)
    if x > 1 - e:
        y = 1 - x; return 1 - vmax * y * y / (2 * e)
    return vmax * (x - e / 2)


def mix(p, q, t):
    return tuple(int(p[i] + (q[i] - p[i]) * t) for i in range(3))


def load_panel(path):
    """render -> float32 (VH, VW, 3); transparent pixels go onto a soft gradient backdrop; gentle saturation lift"""
    im = Image.open(path)
    im = im.convert("RGBA")
    if im.size != (VW, VH):
        im = im.resize((VW, VH), Image.LANCZOS)
    v = [int(t) for t in a.bg.split(",")]
    gy = np.linspace(0, 1, VH, dtype=np.float32)[:, None, None]
    bg = C(v[:3]) * (1 - gy) + C(v[3:]) * gy
    bg = np.broadcast_to(bg, (VH, VW, 3))
    arr = np.asarray(im, np.float32); al = arr[..., 3:4] / 255
    rgb = arr[..., :3] * al + bg * (1 - al)
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    out = ImageEnhance.Color(out).enhance(a.sat)
    return np.asarray(out, np.float32)


def _illu_bg(pal):
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = C((10, 8, 30)) + (C((26, 14, 58)) - C((10, 8, 30))) * (gy / H)[..., None]
    for (cx, cy, col) in ((180, 260, pal[0]), (900, 1640, pal[1])):
        g = np.exp(-((gx - cx) ** 2 + (gy - cy) ** 2) / (2 * 420 ** 2))[..., None]
        bg = bg + C(col) * 0.22 * g
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle((PX - 6, PY - 6, PX + VW + 6, PY + VH + 6), 54, fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    bg = bg + C(pal[0]) * 0.35 * (np.asarray(glow, np.float32) / 255)[..., None]
    return np.clip(bg, 0, 255)


def _text_layer(lines):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for y, s, size, wt, col, sp in lines:
        f = FA(size, wt)
        while d.textlength(s, font=f) + sp * len(s) > W - 80 and size > 14:
            size -= 2; f = FA(size, wt)
        w = d.textlength(s, font=f) + sp * (len(s) - 1); x = (W - w) / 2
        for ch in (s if sp else [s]):
            d.text((x, y), ch, font=f, fill=col); x += d.textlength(ch, font=f) + sp
    return np.asarray(lay, np.float32)


def _pill(y, text, size=40):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); f = FA(size, "demi")
    w = d.textlength(text, font=f)
    d.rounded_rectangle(((W - w) / 2 - 36, y, (W + w) / 2 + 36, y + size + 34), (size + 34) / 2, fill=(255, 255, 255, 38),
                        outline=(255, 255, 255, 90), width=2)
    d.text(((W - w) / 2, y + 12), text, font=f, fill=(255, 255, 255, 255))
    return np.asarray(lay, np.float32)


def _over(im, lay, al=1.0):
    k = lay[..., 3:4] / 255 * al
    return im * (1 - k) + lay[..., :3] * k


def hook_layer(variant):
    big, small = {"dontblink": ("DON'T BLINK", "keep your eyes on the picture"),
                  "keepeyes": ("KEEP YOUR EYES", "ON THE PICTURE")}[variant]
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.rectangle((0, 60, W, 440), fill=(12, 8, 30, 255))
    if variant == "dontblink":
        f = FA(140, "heavy"); tw = d.textlength(big, font=f); d.text(((W - tw) / 2, 110), big, font=f, fill=(255, 255, 255, 255))
        f2 = FA(56, "demi"); tw = d.textlength(small, font=f2); d.text(((W - tw) / 2, 315), small, font=f2, fill=ACC + (255,))
    else:
        for y, txt, col in ((105, big, (255, 255, 255, 255)), (255, small, ACC + (255,))):
            f = FA(110, "heavy"); tw = d.textlength(txt, font=f); d.text(((W - tw) / 2, y), txt, font=f, fill=col)
    return np.asarray(lay, np.float32)


def ring(img, box, col=(255, 50, 70)):
    im2 = img.copy(); dd = ImageDraw.Draw(im2); pad = 18
    dd.ellipse((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad), outline=col, width=9)
    return im2


# ---- panel source
A, B = load_panel(os.path.join(a.work, "A.png")), load_panel(os.path.join(a.work, "B.png")); keys = None
diff = np.abs(A - B).max(2) > 24
ys, xs = np.nonzero(diff)
box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
print("changed fraction %.4f box %s" % (diff.mean(), box))
Ai, Bi = Image.fromarray(A.astype(np.uint8)), Image.fromarray(B.astype(np.uint8))
stem = os.path.splitext(OUT)[0]
ring(Ai, box).save(stem + "_answer_a.png"); ring(Bi, box).save(stem + "_answer_b.png")

pm = Image.new("L", (VW, VH), 0); ImageDraw.Draw(pm).rounded_rectangle((0, 0, VW - 1, VH - 1), 44, fill=255)
bg = _illu_bg((ACC, (120, 140, 255)))
q_txt = _text_layer([(120, "SLOW CHANGE PUZZLE", 34, "demi", ACC + (255,), 10),
                     (175, "SOMETHING IS", 100, "heavy", (255, 255, 255, 255), 0),
                     (290, "SLOWLY CHANGING", 100, "heavy", ACC + (255,), 0)])
sub = _text_layer([(1440, "can you spot it before the timer ends?", 40, "demi", (255, 255, 255, 220), 0)])
cta = _pill(1640, "Comment what changed")
foot = _text_layer([(1800, "Follow for a new puzzle every day", 36, "demi", (255, 255, 255, 170), 0)])
base_q = Image.fromarray(np.clip(_over(_over(_over(_over(bg, q_txt), sub), cta), foot), 0, 255).astype(np.uint8))
hook_l = hook_layer(HOOK)

intro = INTRO if PREV else 0.0
if intro:
    pa = Image.open(PREV["ans_a"]).convert("RGB").resize((VW, VH)); pb = Image.open(PREV["ans_b"]).convert("RGB").resize((VW, VH))
    words = PREV["short"].split(); l1, l2 = " ".join(words[:len(words) // 2 + 1]), " ".join(words[len(words) // 2 + 1:])
    yday = PREV.get("date") == str(TODAY - datetime.timedelta(days=1))
    i_txt = _text_layer([(120, "YESTERDAY'S ANSWER" if yday else "LAST PUZZLE'S ANSWER", 40, "demi", ACC + (255,), 10),
                         (180, l1, 76, "heavy", (255, 255, 255, 255), 0), (285, l2, 76, "heavy", ACC + (255,), 0),
                         (1440, "today's puzzle starts now", 44, "demi", (255, 255, 255, 230), 0)])
    base_i = Image.fromarray(np.clip(_over(_over(bg, i_txt), foot), 0, 255).astype(np.uint8))

_b8 = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26], [12, 44, 4, 36, 14, 46, 6, 38],
                [60, 28, 52, 20, 62, 30, 54, 22], [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], np.float32) / 64 + 1 / 128
_bayer = np.tile(_b8, (VH // 8 + 1, VW // 8 + 1))[:VH, :VW, None]
LA, LB = _s2lin(A), _s2lin(B)
if keys:
    LK = None  # converted lazily

total = intro + CH_T; n = int(total * FPS)
tmp = OUT + ".silent.mp4"
p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                      "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18", "-maxrate", "3000k",
                      "-bufsize", "6M", "-tune", "film", "-x264-params", "keyint=300:min-keyint=300:scenecut=0:deadzone-inter=0:deadzone-intra=0",
                      "-movflags", "+faststart", tmp], stdin=subprocess.PIPE)
sheet = []
for fr in range(n):
    t = fr / FPS
    if t < intro:
        im = base_i.copy(); d = ImageDraw.Draw(im); show_b = int(t / 0.75) % 2 == 1
        im.paste(pb if show_b else pa, (PX, PY), pm)
        lab = "AFTER" if show_b else "BEFORE"; f2 = FA(44, "heavy"); tw = d.textlength(lab, font=f2)
        d.rounded_rectangle((PX + 24, PY + 24, PX + 24 + tw + 40, PY + 92), 34, fill=(20, 16, 40))
        d.text((PX + 44, PY + 28), lab, font=f2, fill=(255, 255, 255))
    else:
        tq = t - intro; f = _ease(tq / (CH_T - 1.0))
        im = base_q.copy(); d = ImageDraw.Draw(im)
        if keys:
            q = f * (len(keys) - 1); k0 = min(int(q), len(keys) - 2); w_ = q - k0
            pan = _lin2s(_s2lin(keys[k0]) * (1 - w_) + _s2lin(keys[k0 + 1]) * w_)
        else:
            pan = _lin2s(LA * (1 - f) + LB * f)
        pan = np.clip(np.floor(pan + _bayer), 0, 255).astype(np.uint8)
        im.paste(Image.fromarray(pan), (PX, PY), pm)
        nn = int(900 * (1 - tq / CH_T))
        d.rounded_rectangle((90, 1395, 990, 1409), 7, fill=(70, 60, 110))
        if nn > 8:
            d.rounded_rectangle((90, 1395, 90 + nn, 1409), 7, fill=mix((120, 140, 255), ACC, nn / 900))
        f3 = FA(60, "heavy"); s = f"{int(CH_T - tq)}s"; tw = d.textlength(s, font=f3); d.text(((W - tw) / 2, 1490), s, font=f3, fill="white")
    if t < HOOK_T:
        al = 1.0 if t < HOOK_T - 0.2 else (HOOK_T - t) / 0.2
        im = Image.fromarray(np.clip(_over(np.asarray(im, np.float32), hook_l, al), 0, 255).astype(np.uint8))
    if fr in (int(0.5 * FPS), int(2 * FPS), int((intro + 1.5) * FPS), int((intro + 15) * FPS), n - 1):
        sheet.append(im.resize((W // 3, H // 3)))
    p.stdin.write(im.tobytes())
p.stdin.close(); p.wait()
if a.music and os.path.exists(a.music):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-stream_loop", "-1", "-i", a.music, "-shortest", "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-af", "afade=t=out:st=%d:d=1.5" % (int(total) - 2),
                    "-movflags", "+faststart", OUT], check=True)
    os.remove(tmp)
else:
    os.replace(tmp, OUT)
sh = Image.new("RGB", (len(sheet) * (W // 3 + 10), H // 3), (0, 0, 0))
for i, s in enumerate(sheet):
    sh.paste(s, (i * (W // 3 + 10), 0))
sh.save(stem + "_sheet.jpg", quality=88)
info = dict(META, type="cg_change", date=str(TODAY), seconds=total, hook=HOOK, box_panel=list(box),
            cover_ms=int((intro + 1.0) * 1000), ans_a=os.path.abspath(stem + "_answer_a.png"),
            ans_b=os.path.abspath(stem + "_answer_b.png"), intro_from=PREV["answer"] if PREV else None, video=os.path.abspath(OUT))
json.dump(info, open(stem + ".json", "w"), indent=1)
print("done", OUT, total)
