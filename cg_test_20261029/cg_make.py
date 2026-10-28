#!/usr/bin/env python3
"""Looply CG slow change, one call = one finished video (render with Blender + compose).
  python3 cg_make.py OUT.mp4 [--state ~/Looply/output/auto/cg_state.json] [--music M.m4a] [--samples 128]
Picks scene / kind so that the change type (colour / vanish / appear) differs from the last CG post and the
scene alternates town / room; never repeats an answer already in the state file. Renders in OUT's folder
(<stem>_work/), then writes OUT.mp4 + OUT.json (cg_video.py). Prints the json path on the last line.
After the post succeeded: python3 cg_video.py --commit OUT.json --state STATE --media-id ID
Blender: $BLENDER, else /Applications/Blender.app/Contents/MacOS/Blender, else the `bpy` module in this python."""
import argparse, json, os, random, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("--state", default=os.path.expanduser("~/Looply/output/auto/cg_state.json"))
ap.add_argument("--music"); ap.add_argument("--samples", type=int, default=128); ap.add_argument("--seed", type=int)
ap.add_argument("--scene"); ap.add_argument("--kind")
a = ap.parse_args()

# town: only colour (its chimneys / trees are too small on screen, tested 2026-10-27); room: colour + vanish / appear
KINDS = {"town": {"wall": "color", "roof": "color"},
         "room": {"art": "color", "cushion": "color", "vanish": "vanish", "appear": "appear"}}
hist = json.load(open(a.state))["history"] if os.path.exists(a.state) else []
last = hist[-1] if hist else {}
rng = random.Random(a.seed)
last_ck = last.get("change_kind")
# colour and non-colour take turns: after a colour change -> room vanish / appear; otherwise a colour change
# (town and room alternate). Kinds used in the last 4 posts are avoided while there is another choice.
recent = [h.get("kind") for h in hist[-4:]]
if a.scene and a.kind:
    plans = [(a.scene, a.kind)]
else:
    if last_ck == "color":
        pool = [("room", k) for k, ck in KINDS["room"].items() if ck != "color"]
    else:
        pool = [(s, k) for s in KINDS for k, ck in KINDS[s].items() if ck == "color" and s != last.get("scene")]
    pool = [p for p in pool if not a.scene or p[0] == a.scene] or pool
    rng.shuffle(pool)
    pool.sort(key=lambda p: p[1] in recent)
    plans = pool + [(s, k) for s in KINDS for k in KINDS[s] if (s, k) not in pool]  # last resort: anything

stem = os.path.splitext(a.out)[0]
work = stem + "_work"; os.makedirs(work, exist_ok=True)
if os.path.exists(os.path.join(work, "meta.json")):
    os.remove(os.path.join(work, "meta.json"))
avoid = os.path.join(work, "avoid.txt")
with open(avoid, "w") as f:
    for h in hist:
        f.write(h.get("short", "") + "\n" + h.get("answer", "") + "\n")

blender = os.environ.get("BLENDER") or "/Applications/Blender.app/Contents/MacOS/Blender"
for scene, kind in plans[:3]:  # up to 3 scene / kind tries (each with its own seed)
    seed = a.seed if a.seed is not None else rng.randrange(1, 10 ** 6)
    args = [work, "--seed", str(seed), "--scene", scene, "--kind", kind, "--samples", str(a.samples), "--avoid", avoid]
    if os.path.exists(blender):
        cmd = [blender, "-b", "--factory-startup", "--python", os.path.join(HERE, "cg_render.py"), "--"] + args
    else:
        cmd = [sys.executable, os.path.join(HERE, "cg_render.py")] + args
    print("render:", scene, kind, seed, flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    for line in (p.stdout + p.stderr).splitlines():
        if line.startswith("CG ") or "Error" in line:
            print(line, flush=True)
    if os.path.exists(os.path.join(work, "meta.json")):
        break
else:
    sys.exit("cg_render failed for every try")
v = [sys.executable, os.path.join(HERE, "cg_video.py"), work, a.out, "--state", a.state]
if a.music:
    v += ["--music", a.music]
subprocess.run(v, check=True)
print(stem + ".json")
