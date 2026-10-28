"""Looply CG slow change: short answer-only video that closes the CG chain (the last CG post's answer).
  python3 cg_answer.py OUT.mp4 --state ~/Looply/output/auto/cg_state.json [--music M.m4a] [--seconds 8]
Before / after of the last committed CG answer flip every 0.75 s, with the answer text; same look as the
3s intro of the slow-change videos. Writes OUT.mp4 and OUT_sheet.jpg."""
import argparse, datetime, json, os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
VW, VH = 1000, 900
PX, PY = (W - VW) // 2, 450
ACC = (255, 196, 90)
AVENIR = "/System/Library/Fonts/Avenir Next.ttc"
FONTS = {"heavy": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "demi": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"}

ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("--state", required=True); ap.add_argument("--music")
ap.add_argument("--seconds", type=float, default=8.0); ap.add_argument("--today")
a = ap.parse_args()
prev = json.load(open(a.state))["history"][-1]


def FA(size, wt="heavy"):
    try:
        return ImageFont.truetype(AVENIR, size, index={"heavy": 8, "demi": 2}[wt])
    except Exception:
        return ImageFont.truetype(FONTS[wt], size)


def C(c):
    return np.array(c, np.float32)


def bg_img(pal):
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = C((10, 8, 30)) + (C((26, 14, 58)) - C((10, 8, 30))) * (gy / H)[..., None]
    for (cx, cy, col) in ((180, 260, pal[0]), (900, 1640, pal[1])):
        g = np.exp(-((gx - cx) ** 2 + (gy - cy) ** 2) / (2 * 420 ** 2))[..., None]
        bg = bg + C(col) * 0.22 * g
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).rounded_rectangle((PX - 6, PY - 6, PX + VW + 6, PY + VH + 6), 54, fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    bg = bg + C(pal[0]) * 0.35 * (np.asarray(glow, np.float32) / 255)[..., None]
    return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))


def ctext(d, y, s, size, wt, col, sp=0):
    f = FA(size, wt)
    while d.textlength(s, font=f) + sp * len(s) > W - 80 and size > 14:
        size -= 2; f = FA(size, wt)
    w = d.textlength(s, font=f) + sp * (len(s) - 1); x = (W - w) / 2
    for ch in (s if sp else [s]):
        d.text((x, y), ch, font=f, fill=col); x += d.textlength(ch, font=f) + sp


base = bg_img((ACC, (120, 140, 255))); d = ImageDraw.Draw(base)
TODAY = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
yday = prev.get("date") == str(TODAY - datetime.timedelta(days=1))
words = prev["short"].split(); l1, l2 = " ".join(words[:len(words) // 2 + 1]), " ".join(words[len(words) // 2 + 1:])
ctext(d, 120, "YESTERDAY'S ANSWER" if yday else "LAST PUZZLE'S ANSWER", 40, "demi", ACC, 10)
ctext(d, 180, l1, 76, "heavy", (255, 255, 255)); ctext(d, 285, l2, 76, "heavy", ACC)
ctext(d, 1440, "did you spot it in time?", 44, "demi", (255, 255, 255))
ctext(d, 1560, "comment how many seconds it took you", 38, "demi", (255, 255, 255))
ctext(d, 1800, "Follow for a new puzzle every day", 36, "demi", (200, 200, 210))
pa = Image.open(prev["ans_a"]).convert("RGB").resize((VW, VH)); pb = Image.open(prev["ans_b"]).convert("RGB").resize((VW, VH))
pm = Image.new("L", (VW, VH), 0); ImageDraw.Draw(pm).rounded_rectangle((0, 0, VW - 1, VH - 1), 44, fill=255)
n = int(a.seconds * FPS)
tmp = a.out + ".silent.mp4"
p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                      "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18", "-maxrate", "3000k",
                      "-bufsize", "6M", "-movflags", "+faststart", tmp], stdin=subprocess.PIPE)
frames = []
for fr in range(n):
    t = fr / FPS; show_b = int(t / 0.75) % 2 == 1
    im = base.copy(); dd = ImageDraw.Draw(im); im.paste(pb if show_b else pa, (PX, PY), pm)
    lab = "AFTER" if show_b else "BEFORE"; f2 = FA(44, "heavy"); tw = dd.textlength(lab, font=f2)
    dd.rounded_rectangle((PX + 24, PY + 24, PX + 24 + tw + 40, PY + 92), 34, fill=(20, 16, 40))
    dd.text((PX + 44, PY + 28), lab, font=f2, fill=(255, 255, 255))
    if fr in (10, 30):
        frames.append(im.resize((W // 3, H // 3)))
    p.stdin.write(im.tobytes())
p.stdin.close(); p.wait()
if a.music and os.path.exists(a.music):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-stream_loop", "-1", "-i", a.music, "-shortest", "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-af", "afade=t=out:st=%d:d=1.5" % (int(a.seconds) - 2),
                    "-movflags", "+faststart", a.out], check=True)
    os.remove(tmp)
else:
    os.replace(tmp, a.out)
sh = Image.new("RGB", (2 * (W // 3 + 10), H // 3))
for i, f in enumerate(frames):
    sh.paste(f, (i * (W // 3 + 10), 0))
sh.save(os.path.splitext(a.out)[0] + "_sheet.jpg", quality=88)
print("done", a.out)
