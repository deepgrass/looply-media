# Animal collage slow-change preview (vanish or move), Looply house style.
# usage: python3 make_animals.py SRC_DIR OUT_DIR MODE(vanish|move) [AUDIO] [SEED]
import sys, os, glob, subprocess, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SRC, OUT, MODE = sys.argv[1:4]
AUD = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != '-' else None
SEED = int(sys.argv[5]) if len(sys.argv) > 5 else 3
os.makedirs(OUT, exist_ok=True)
S = 1.5                      # 720x1280 house layout scaled to 1080x1920
W, H, FPS, DUR = int(720 * S), int(1280 * S), 30, 30
T0, T1 = 2.0, 27.0

# ---------- fonts ----------
def find_font(names):
    dirs = [os.path.expanduser('~/Library/Fonts'), '/Library/Fonts', '/System/Library/Fonts',
            '/System/Library/Fonts/Supplemental', '/usr/share/fonts/opentype/inter', '/usr/share/fonts/truetype/dejavu']
    for n in names:
        for d in dirs:
            p = os.path.join(d, n)
            if os.path.exists(p): return p
        g = glob.glob(os.path.expanduser('~/Looply/**/' + n), recursive=True)
        if g: return g[0]
    raise SystemExit('font not found: %s' % names)
FB = {'semi': find_font(['Inter-SemiBold.otf', 'Inter-SemiBold.ttf', 'Arial Bold.ttf', 'DejaVuSans-Bold.ttf']),
      'xb': find_font(['Inter-ExtraBold.otf', 'Inter-ExtraBold.ttf', 'Arial Black.ttf', 'Arial Bold.ttf', 'DejaVuSans-Bold.ttf']),
      'bold': find_font(['Inter-Bold.otf', 'Inter-Bold.ttf', 'Arial Bold.ttf', 'DejaVuSans-Bold.ttf'])}
print('fonts', FB)
fx = lambda k, s: ImageFont.truetype(FB[k], int(s * S))

# ---------- house background (same as corgi v2) ----------
y = np.linspace(0, 1, H)[:, None, None]; x = np.linspace(0, 1, W)[None, :, None]
bgarr = np.array([42, 30, 40]) * (1 - y) + np.array([44, 34, 110]) * y + np.array([10, 0, 25]) * x
bg = Image.fromarray(np.broadcast_to(bgarr, (H, W, 3)).astype(np.uint8))
d = ImageDraw.Draw(bg)
def ctext(dr, yy, t, f, fill, sp=0):
    yy *= S
    if sp:
        sp *= S; ws = [dr.textlength(c, font=f) for c in t]; xx = (W - sum(ws) - sp * (len(t) - 1)) / 2
        for c, w in zip(t, ws): dr.text((xx, yy), c, font=f, fill=fill); xx += w + sp
    else:
        dr.text(((W - dr.textlength(t, font=f)) / 2, yy), t, font=f, fill=fill)
ctext(d, 82, 'SLOW CHANGE PUZZLE', fx('semi', 22), (240, 190, 90), sp=5)
ctext(d, 122, 'SOMETHING IS', fx('xb', 64), (255, 255, 255))
ctext(d, 198, 'SLOWLY CHANGING', fx('xb', 64), (250, 192, 80))
ctext(d, 962, 'can you spot it before the timer ends?', fx('semi', 25), (235, 235, 245))
ctext(d, 1200, 'Follow for a new puzzle every day', fx('semi', 22), (175, 170, 205))
pf = fx('semi', 25); pt = 'Comment what changed'; pw = d.textlength(pt, font=pf) + 50 * S
d.rounded_rectangle(((W - pw) / 2, 1094 * S, (W + pw) / 2, 1142 * S), int(24 * S), fill=(70, 60, 120), outline=(120, 110, 170), width=1)
ctext(d, 1103, pt, pf, (255, 255, 255))
CX0, CY0, CW, CH = int(27 * S), int(300 * S), int(666 * S), int(600 * S)
glow = Image.new('L', (W, H), 0); ImageDraw.Draw(glow).rounded_rectangle((CX0, CY0, CX0 + CW, CY0 + CH), int(22 * S), fill=120)
glow = glow.filter(ImageFilter.GaussianBlur(14 * S))
bg = Image.composite(Image.new('RGB', (W, H), (250, 200, 120)), bg, glow.point(lambda v: v * 0.6))
cm = Image.new('L', (CW, CH), 0); ImageDraw.Draw(cm).rounded_rectangle((0, 0, CW - 1, CH - 1), int(22 * S), fill=255)

# ---------- scene backdrop: soft studio sweep ----------
yy = np.linspace(0, 1, CH)[:, None, None]; xx = np.linspace(-1, 1, CW)[None, :, None]
wall = np.array([236, 228, 214]) * (1 - yy) + np.array([246, 240, 230]) * yy
floor_t = np.clip((yy - 0.30) / 0.25, 0, 1)
scene_bg = wall * (1 - floor_t) + np.array([226, 214, 196]) * floor_t
scene_bg = scene_bg * (1 - 0.10 * xx ** 2) * (1 - 0.06 * (1 - yy))
scene_bg = np.broadcast_to(scene_bg, (CH, CW, 3)).astype(np.float32)

# ---------- animals ----------
PICK = ['001_01', '002_01', '004_01', '006_02', '009_01', '014_01', '016_01', '017_01', '020_01',
        '021_02', '024_01', '028_02', '029_01', '053_01', '026_01', '015_01', '023_01', '032_01']
files = {}
for k in PICK:
    g = sorted(glob.glob(os.path.join(SRC, k + '_*.png')))
    if g: files[k] = g[0]
print('available', len(files), list(files))
rng = np.random.default_rng(SEED)
keys = list(files); rng.shuffle(keys)
ROWS = [(0.42, 0.30, 4), (0.69, 0.32, 4), (0.97, 0.36, 3)]   # baseline y, height, count (back -> front)
need = sum(r[2] for r in ROWS)
if len(keys) < need: raise SystemExit('not enough animals: %d' % len(keys))
keys = keys[:need]

def load(p, hpx, wmax):
    im = Image.open(p).convert('RGBA'); im = im.crop(im.getchannel('A').getbbox())
    sc = min(hpx / im.height, wmax / im.width)
    return im.resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.LANCZOS)

layers = []   # (rgba float array, x, y) in z order
gi = 0
for ri, (by, hf, n) in enumerate(ROWS):
    slot = CW / n
    for j in range(n):
        im = load(files[keys[gi]], hf * CH, slot * 1.12)
        cx = slot * (j + 0.5) + rng.uniform(-0.08, 0.08) * slot
        bx = by * CH + rng.uniform(-0.015, 0.015) * CH
        x0, y0 = int(cx - im.width / 2), int(bx - im.height)
        layers.append(dict(key=keys[gi], im=np.asarray(im).astype(np.float32) / 255, x=x0, y=y0, row=ri, j=j))
        gi += 1

def shadow(L):
    a = L['im'][..., 3]; h, w = a.shape
    sh = np.zeros((CH, CW), np.float32)
    # soft contact ellipse under the feet
    m = Image.new('L', (CW, CH), 0)
    ex0, ex1 = L['x'] + w * 0.12, L['x'] + w * 0.88; ey = L['y'] + h
    ImageDraw.Draw(m).ellipse((ex0, ey - h * 0.05, ex1, ey + h * 0.04), fill=150)
    sh += np.asarray(m.filter(ImageFilter.GaussianBlur(h * 0.035))).astype(np.float32) / 255
    return np.clip(sh, 0, 0.6)
for L in layers: L['sh'] = shadow(L)

def pick_target():
    mids = [L for L in layers if L['row'] == 1 and L['j'] in (1, 2)]
    return mids[SEED % len(mids)]
TG = pick_target()
print('target', TG['key'], 'mode', MODE)
DX = 0
if MODE == 'move':
    # shift the target sideways by ~35% of its own width, toward the frame centre side with more room
    w = TG['im'].shape[1]; DX = int(w * 0.35) * (1 if TG['j'] == 1 else -1)

def paste(dst, L, alpha, dx=0):
    a = L['im']; h, w = a.shape[:2]; x0, y0 = L['x'] + dx, L['y']
    xs, ys = max(0, x0), max(0, y0); xe, ye = min(CW, x0 + w), min(CH, y0 + h)
    if xe <= xs or ye <= ys: return
    sub = a[ys - y0:ye - y0, xs - x0:xe - x0]
    al = sub[..., 3:4] * alpha
    dst[ys:ye, xs:xe] = dst[ys:ye, xs:xe] * (1 - al) + sub[..., :3] * 255 * al

def scene(u):
    f = scene_bg.copy()
    for L in layers:
        k = 1.0; dx = 0
        if L is TG:
            if MODE == 'vanish': k = 1 - u
            else: dx = int(round(DX * u))
        sh = L['sh'] if dx == 0 else np.roll(L['sh'], dx, axis=1)
        f *= (1 - 0.55 * sh * k)[..., None]
    for L in layers:
        if L is TG:
            if MODE == 'vanish': paste(f, L, 1 - u)
            else: paste(f, L, 1.0, DX * u)
        else:
            paste(f, L, 1.0)
    return f

def paste_float(dst, L, dxf):
    # sub-pixel move: blend two integer offsets
    i = int(np.floor(dxf)); fr = dxf - i
    a = dst.copy(); b = dst.copy()
    paste(a, L, 1.0, i); paste(b, L, 1.0, i + 1)
    dst[:] = a * (1 - fr) + b * fr
if MODE == 'move':
    def scene(u):
        f = scene_bg.copy()
        for L in layers:
            sh = L['sh'] if L is not TG else np.roll(L['sh'], int(round(DX * u)), axis=1)
            f *= (1 - 0.55 * sh)[..., None]
        for L in layers:
            if L is TG: paste_float(f, L, DX * u)
            else: paste(f, L, 1.0)
        return f

A, B = scene(0.0), scene(1.0)
Image.fromarray(A.astype(np.uint8)).save(os.path.join(OUT, 'scene_start.png'))
Image.fromarray(B.astype(np.uint8)).save(os.path.join(OUT, 'scene_end.png'))
sep = np.full((CH, 20, 3), 255, np.float32)
Image.fromarray(np.hstack([A, sep, B]).astype(np.uint8)).save(os.path.join(OUT, 'before_after.jpg'), quality=92)

name = os.path.join(OUT, 'animals_%s.mp4' % MODE)
cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-']
if AUD: cmd += ['-i', AUD, '-map', '0:v', '-map', '1:a', '-shortest', '-c:a', 'aac', '-b:a', '128k']
cmd += ['-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-maxrate', '6000k', '-bufsize', '12000k',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', name]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
tf = fx('bold', 38); drng = np.random.default_rng(0)
for i in range(FPS * DUR):
    t = i / FPS
    u = min(max((t - T0) / (T1 - T0), 0), 1); u = u * u * (3 - 2 * u)
    if MODE == 'vanish': img = A * (1 - u) + B * u          # exact: only the target layer differs
    else: img = scene(u)
    img = np.clip(img + drng.uniform(-0.5, 0.5, img.shape), 0, 255)
    fr = bg.copy(); fr.paste(Image.fromarray(img.astype(np.uint8)), (CX0, CY0), cm)
    dr = ImageDraw.Draw(fr)
    dr.rounded_rectangle((60 * S, 930 * S, 660 * S, 940 * S), int(5 * S), fill=(70, 62, 120))
    rem = 1 - t / DUR
    dr.rounded_rectangle((60 * S, 930 * S, (60 + max(10, 600 * rem)) * S, 940 * S), int(5 * S),
                         fill=(250, 192, 80) if rem > 0.1 else (130, 120, 240))
    ctext(dr, 1000, f'{max(1, int(np.ceil(DUR - t)))}s', tf, (255, 255, 255))
    if i == 0: fr.save(os.path.join(OUT, 'frame_start_%s.jpg' % MODE), quality=90)
    p.stdin.write(fr.tobytes())
p.stdin.close(); p.wait()
print('done', name, 'target', TG['key'])
