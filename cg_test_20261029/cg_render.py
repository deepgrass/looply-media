"""Looply CG slow change: render the start / end panels (1000x900) of one change in a procedural 3D scene.
All geometry is built here from primitives (original art, no assets). Cycles CPU.

  blender -b --python cg_render.py -- OUTDIR --seed N [--scene town|room] [--kind K] [--samples 128] [--avoid FILE]
  (or: python3 cg_render.py OUTDIR ... with the `bpy` pip module)

Writes OUTDIR/A.png, OUTDIR/B.png (start / end) and OUTDIR/meta.json:
  {scene, mood, kind, change_kind (color|light|vanish|appear), answer, short, frac, box}
Kinds: town: wall, roof, lights (sunset only), vanish_tree, appear_chimney
       room: art, cushion, book, vanish (small object), appear (small object)
The change is checked on the pixels: 0.6%..5% of the panel (else another candidate is tried, up to TRIES)."""
import argparse, json, math, os, random, sys
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument("out"); ap.add_argument("--seed", type=int, default=1); ap.add_argument("--scene")
ap.add_argument("--kind"); ap.add_argument("--samples", type=int, default=128); ap.add_argument("--avoid")
ap.add_argument("--tries", type=int, default=6)
ap.add_argument("--min", type=float, default=0.02); ap.add_argument("--max", type=float, default=0.07)
A = ap.parse_args(argv)
os.makedirs(A.out, exist_ok=True)
rng = random.Random(A.seed)
AVOID = set()
if A.avoid and os.path.exists(A.avoid):
    AVOID = {l.strip().upper() for l in open(A.avoid) if l.strip()}
MIN_FRAC, MAX_FRAC = A.min, A.max  # same rule as the illustrated slow change: 2-7% of the panel

TOWN_KINDS = ["wall", "roof", "appear_tree", "appear_chimney", "vanish_chimney"]
ROOM_KINDS = ["sofa", "rug", "art", "cushion", "vanish", "appear"]
HARBOR_KINDS = ["hull", "hwall"]
FARM_KINDS = ["barn", "barnroof", "farmhouse", "field", "silo"]
SCENE_KINDS = {"town": TOWN_KINDS, "room": ROOM_KINDS, "harbor": HARBOR_KINDS, "farm": FARM_KINDS}
CHANGE_KIND = {"wall": "color", "roof": "color", "art": "color", "cushion": "color", "book": "color",
               "appear_tree": "appear", "vanish_chimney": "vanish", "vanish": "vanish", "appear_chimney": "appear", "appear": "appear"}
for k in HARBOR_KINDS + FARM_KINDS + ["sofa", "rug"]:
    CHANGE_KIND[k] = "color"
scene_name = A.scene or (next(s for s, ks in SCENE_KINDS.items() if A.kind in ks) if A.kind else rng.choice(list(SCENE_KINDS)))
kind = A.kind or rng.choice(SCENE_KINDS[scene_name])

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def srgb(c):
    return tuple(((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92 for v in c)


def bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def mat(name, col, rough=0.6, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = bsdf(m)
    b.inputs["Base Color"].default_value = (*srgb(col), 1)
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    return m


def set_col(m, col):
    bsdf(m).inputs["Base Color"].default_value = (*srgb(col), 1)


def set_emit(m, col, strength):
    b = bsdf(m)
    key = "Emission Color" if "Emission Color" in b.inputs else "Emission"
    b.inputs[key].default_value = (*srgb(col), 1); b.inputs["Emission Strength"].default_value = strength


def box(name, loc, size, m, bevel=0.03, rot=(0, 0, 0), segs=2):
    bpy.ops.mesh.primitive_cube_add(location=loc, rotation=rot)
    o = bpy.context.object; o.name = name; o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        md = o.modifiers.new("b", "BEVEL"); md.width = bevel; md.segments = segs
    o.data.materials.append(m); return o


def cyl(name, loc, r, h, m, verts=24, r2=None, rot=(0, 0, 0), smooth=True):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=loc, rotation=rot)
    o = bpy.context.object; o.name = name; o.data.materials.append(m)
    if smooth:
        bpy.ops.object.shade_smooth()
    return o


def blob(name, loc, r, m, sub=1, squash=1.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    o = bpy.context.object; o.name = name; o.scale.z = squash; o.data.materials.append(m)
    return o


def sphere(name, loc, r, m, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    o = bpy.context.object; o.name = name; o.scale = scale; o.data.materials.append(m)
    bpy.ops.object.shade_smooth(); return o


def prism(name, loc, w, d, h, m, over=0.18):
    w2, d2 = w / 2 + over, d / 2 + over
    verts = [(-w2, -d2, 0), (w2, -d2, 0), (w2, d2, 0), (-w2, d2, 0), (-w2, 0, h), (w2, 0, h)]
    faces = [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    o = bpy.data.objects.new(name, me); sc.collection.objects.link(o); o.location = loc
    o.modifiers.new("s", "SOLIDIFY").thickness = 0.12
    md = o.modifiers.new("b", "BEVEL"); md.width = 0.03; md.segments = 2
    o.data.materials.append(m); return o


def group(objs, name):
    bpy.ops.object.empty_add(location=objs[0].location); e = bpy.context.object; e.name = name
    for o in objs:
        o.parent = e; o.matrix_parent_inverse = e.matrix_world.inverted()
    return e


def hide(objs, flag):
    for o in objs:
        o.hide_render = flag
        for c in o.children_recursive:
            c.hide_render = flag


# colour names used in the answer text (all well apart in hue / lightness)
NAMED = {"cream": (246, 236, 212), "peach": (240, 196, 160), "pale blue": (196, 220, 238), "mint": (200, 230, 206),
         "lilac": (222, 206, 238), "yellow": (248, 218, 130), "pink": (240, 186, 196), "sage": (196, 210, 170),
         "red": (186, 64, 52), "grey": (104, 98, 108), "blue": (64, 98, 150), "brown": (146, 96, 62),
         "orange": (204, 116, 64), "green": (78, 120, 84), "purple": (116, 84, 140), "teal": (52, 128, 132),
         "white": (240, 240, 236), "navy": (44, 54, 92), "mustard": (214, 166, 54), "coral": (232, 120, 104),
         "golden": (222, 186, 92), "lime": (150, 196, 84), "dark green": (66, 112, 58), "brown soil": (140, 100, 70),
         "barn red": (168, 52, 44), "sky blue": (120, 176, 220), "turquoise": (64, 170, 170), "olive": (130, 130, 70)}
WALL_NAMES = ["cream", "peach", "pale blue", "mint", "lilac", "yellow", "pink", "sage"]
ROOF_NAMES = ["red", "grey", "blue", "brown", "orange", "green"]


def other_name(cur, pool, far=90):
    """a different colour from the pool, clearly apart from the current one (sage -> cream was too faint)"""
    dist = lambda n: sum((x - y) ** 2 for x, y in zip(NAMED[n], NAMED[cur])) ** 0.5
    return rng.choice([n for n in pool if n != cur and dist(n) >= far] or [n for n in pool if n != cur])


# ================================================================= TOWN
def build_town(mood):
    M = {k: mat(k, c, r) for k, c, r in [
        ("grass", (122, 170, 92) if mood == "day" else (118, 150, 84), 0.9), ("road", (86, 88, 96), 0.85),
        ("walk", (206, 200, 188), 0.8), ("glass", (60, 84, 110), 0.15), ("frame", (248, 248, 244), 0.5),
        ("door", (120, 78, 54), 0.6), ("trunk", (110, 80, 56), 0.8), ("leaf1", (86, 150, 70), 0.8),
        ("leaf2", (110, 168, 64), 0.8), ("leaf3", (64, 128, 78), 0.8), ("line", (246, 240, 220), 0.6),
        ("lamp", (40, 44, 52), 0.4), ("chim", (150, 90, 70), 0.8), ("tyre", (30, 30, 34), 0.7),
        ("hedge", (72, 132, 66), 0.9), ("stone", (170, 166, 160), 0.8)]}
    T = dict(houses=[], trees=[])
    box("ground", (0, 0, -0.1), (80, 80, 0.2), M["grass"], bevel=0)
    box("road", (0, 0, 0.01), (80, 5.0, 0.04), M["road"], bevel=0)
    for y in (-3.2, 3.2):
        box("walk", (0, y, 0.06), (80, 1.4, 0.12), M["walk"], bevel=0.02)
    for x in range(-30, 31, 3):
        box("dash", (x, 0, 0.035), (1.4, 0.16, 0.01), M["line"], bevel=0)

    def house(x, y, w, d, h, wname, rname, tag, z0, row):
        wm = mat(f"wall_{tag}", NAMED[wname], 0.75); rm = mat(f"roof_{tag}", NAMED[rname], 0.55)
        gm = mat(f"glass_{tag}", (60, 84, 110), 0.15)
        box(f"house_{tag}", (x, y, z0 + h / 2), (w, d, h), wm, bevel=0.05)
        prism(f"roof_{tag}", (x, y, z0 + h), w, d, 0.55 * d, rm)
        fy = y - d / 2
        box("door", (x + rng.uniform(-0.2, 0.2) * w, fy - 0.03, z0 + 0.55), (0.55, 0.08, 1.1), M["door"], bevel=0.02)
        nwin = max(1, int(w / 1.3)); wins = 0
        for i in range(nwin):
            wx = x - w / 2 + (i + 0.5) * w / nwin
            for wz in ([h * 0.72] if h < 2.8 else [h * 0.42 + 0.3, h * 0.78]):
                if abs(wx - x) < 0.5 and wz < 1.6:
                    continue
                box("wf", (wx, fy - 0.03, z0 + wz), (0.62, 0.06, 0.66), M["frame"], bevel=0.01)
                box("wg", (wx, fy - 0.06, z0 + wz), (0.48, 0.04, 0.52), gm, bevel=0); wins += 1
        cx_ = x + rng.choice([-1, 1]) * w * 0.25  # on the front slope, so the camera sees it
        chim = box(f"chim_{tag}", (cx_, y - 0.22 * d, z0 + h + 0.32 * d), (0.42, 0.42, 1.0), M["chim"], bevel=0.02)
        has_chim = rng.random() < 0.5
        chim.hide_render = not has_chim
        T["houses"].append(dict(tag=tag, row=row, x=x, y=y, w=w, d=d, h=h, z0=z0, wall=wm, roof=rm, glass=gm, wins=wins,
                                wname=wname, rname=rname, chim=chim, has_chim=has_chim))

    def tree(x, y, s, z0=0.0, row=-1):
        lm = M[rng.choice(["leaf1", "leaf2", "leaf3"])]
        objs = [cyl("trunk", (x, y, z0 + 0.5 * s), 0.09 * s, 1.0 * s, M["trunk"], 8, smooth=False),
                blob("leaf", (x, y, z0 + 1.35 * s), 0.6 * s, lm, 1),
                blob("leaf", (x + 0.25 * s, y + 0.1 * s, z0 + 1.1 * s), 0.42 * s, lm, 1)]
        T["trees"].append(dict(objs=objs, row=row, pos=Vector((x, y, z0 + 1.0 * s))))

    tag = 0
    for ri, (yy, zz) in enumerate([(6.4, 0.0), (13.0, 1.3), (19.2, 2.6), (25.0, 3.9)]):
        if zz > 0:
            box("terrace", (0, yy + 1.0, zz / 2 - 0.1), (90, 6.4, zz), M["grass"], bevel=0.0)
            box("wallstone", (0, yy - 2.2, zz / 2 - 0.1), (90, 0.3, zz), M["stone"], bevel=0.0)
        x = -21.0 + rng.uniform(0, 1.5)
        while x < 21:
            w = rng.uniform(2.2, 3.4); d = rng.uniform(2.6, 3.2); h = rng.choice([2.2, 2.4, 3.2, 3.4])
            house(x + w / 2, yy + 0.4, w, d, h, rng.choice(WALL_NAMES), rng.choice(ROOF_NAMES), tag, zz, ri); tag += 1
            gap = rng.uniform(0.8, 1.7)
            if rng.random() < 0.55:
                tree(x + w + gap / 2, yy + 1.4, rng.uniform(1.0, 1.4), zz, ri)
            elif 0 < ri < 3 and gap > 1.1:  # a gap that could hold a tree (hidden, for "a tree appeared")
                t0 = len(T["trees"]); tree(x + w + gap / 2, yy - 0.6, rng.uniform(1.3, 1.6), zz, ri)
                T["trees"][t0]["spot"] = True; hide(T["trees"][t0]["objs"], True)
            x += w + gap
    for i in range(60):
        tree(rng.uniform(-30, 30), rng.uniform(28.5, 40), rng.uniform(1.6, 2.6), 3.9, 9)
    box("hill", (0, 34, 3.8), (90, 12, 0.2), M["grass"], bevel=0)
    mnt = mat("mnt", (96, 140, 120), 0.9); mnt2 = mat("mnt2", (120, 160, 170), 0.9)
    for i in range(9):
        blob("mountain", (-60 + i * 15 + rng.uniform(-4, 4), 75 + rng.uniform(0, 15), 0), rng.uniform(14, 22),
             mnt if i % 2 else mnt2, 2, rng.uniform(0.55, 0.85))
    for x in range(-16, 17, 2):
        if rng.random() < 0.5:
            box("hedge", (x + 0.9, -4.4, 0.3), (1.6, 0.5, 0.6), M["hedge"], bevel=0.12)
    lampm = mat("bulb", (250, 246, 230), 0.4)
    for x in range(-15, 16, 6):
        cyl("pole", (x, 3.7, 1.4), 0.05, 2.8, M["lamp"], 8)
        b = blob("bulb", (x, 3.7, 2.85), 0.16, lampm, 2)
    if mood == "sunset":
        set_emit(lampm, (255, 210, 150), 6.0)
    cars = rng.sample([(200, 60, 50), (60, 110, 180), (230, 220, 210), (240, 190, 60), (70, 140, 90)], 3)
    for (cx, cy), col in zip([(-6.5 + rng.uniform(-3, 3), 1.6), (4.2 + rng.uniform(-3, 3), -1.6), (11 + rng.uniform(-2, 2), 1.6)], cars):
        cm = mat("car", col, 0.25, 0.1)
        box("car", (cx, cy, 0.45), (2.2, 1.0, 0.5), cm, bevel=0.15)
        box("cab", (cx - 0.1, cy, 0.85), (1.2, 0.9, 0.4), M["glass"], bevel=0.12)
        for dx in (-0.7, 0.7):
            for dy in (-0.5, 0.5):
                o = cyl("tyre", (cx + dx, cy + dy, 0.22), 0.22, 0.16, M["tyre"], 16); o.rotation_euler.x = math.pi / 2

    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    if mood == "day":
        bg.inputs[0].default_value = (0.36, 0.6, 1.0, 1); bg.inputs[1].default_value = 1.1
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), math.radians(10), math.radians(-35)))
        s = bpy.context.object.data; s.energy = 2.6; s.angle = math.radians(4); s.color = (1.0, 0.93, 0.82)
    else:
        bg.inputs[0].default_value = (*srgb((250, 170, 140)), 1); bg.inputs[1].default_value = 0.55
        bpy.ops.object.light_add(type="SUN", rotation=(math.radians(76), math.radians(4), math.radians(-60)))
        s = bpy.context.object.data; s.energy = 2.2; s.angle = math.radians(3); s.color = (1.0, 0.68, 0.42)
    bpy.ops.object.camera_add(location=(rng.uniform(-3, 3), -12.0, 8.6)); cam = bpy.context.object; sc.camera = cam
    cam.data.lens = 35
    cam.rotation_euler = ((Vector((cam.location.x * 0.6, 13.0, 2.6)) - cam.location).to_track_quat("-Z", "Y").to_euler())
    T["exposure"] = 0.45 if mood == "day" else 0.75
    return T


def town_candidates(T, kind, mood):
    """list of (apply_fn(end: bool), answer, short) in random order"""
    out = []
    cam = sc.camera
    bpy.context.view_layer.update()

    def onscreen(v, lo=0.08, hi=0.92):
        p = world_to_camera_view(sc, cam, v)
        return lo < p.x < hi and 0.12 < p.y < 0.9

    rows = (0, 1) if kind == "wall" else (0, 1, 2)
    cam.data.lens = 42  # closer view so one house is 2-7% of the panel
    hs = [h for h in T["houses"] if h["row"] in rows and onscreen(Vector((h["x"], h["y"] - h["d"] / 2, h["z0"] + h["h"] / 2)))]
    dg = bpy.context.evaluated_depsgraph_get()

    def seen(h, part):
        """share of a 6x6 grid on the house front (or front roof slope) that the camera actually sees"""
        name = f"house_{h['tag']}" if part == "wall" else f"roof_{h['tag']}"
        hit = 0
        for i in range(6):
            for j in range(6):
                u, v = (i + 0.5) / 6, (j + 0.5) / 6
                if part == "wall":
                    pt = Vector((h["x"] - h["w"] / 2 + u * h["w"], h["y"] - h["d"] / 2 - 0.01, h["z0"] + v * h["h"]))
                else:
                    pt = Vector((h["x"] - h["w"] / 2 + u * h["w"], h["y"] - h["d"] / 2 + v * h["d"] / 2,
                                 h["z0"] + h["h"] + 0.12 + v * 0.55 * h["d"]))
                dvec = (pt - cam.location); dist = dvec.length
                ok, loc, nrm, idx, obj, mtx = sc.ray_cast(dg, cam.location, dvec.normalized(), distance=dist + 0.3)
                hit += ok and obj is not None and obj.name == name
        return hit / 36
    part = "roof" if kind == "roof" else "wall"
    if kind in ("wall", "roof"):
        hs = [h for h in hs if seen(h, part) >= 0.6]  # mostly visible, not hidden behind the row in front
    rng.shuffle(hs)
    for h in hs:
        if kind == "wall":
            new = other_name(h["wname"], WALL_NAMES)
            out.append((lambda e, h=h, new=new: set_col(h["wall"], NAMED[new if e else h["wname"]]),
                        f"the {h['wname']} house turned {new}", f"THE {h['wname'].upper()} HOUSE TURNED {new.upper()}"))
        elif kind == "roof":
            new = other_name(h["rname"], ROOF_NAMES)
            out.append((lambda e, h=h, new=new: set_col(h["roof"], NAMED[new if e else h["rname"]]),
                        f"a {h['rname']} roof turned {new}", f"A {h['rname'].upper()} ROOF TURNED {new.upper()}"))
        elif kind == "vanish_chimney" and h["has_chim"]:
            out.append((lambda e, h=h: setattr(h["chim"], "hide_render", e),
                        f"the chimney on the {h['wname']} house disappeared", f"THE CHIMNEY ON THE {h['wname'].upper()} HOUSE DISAPPEARED"))
        elif kind == "appear_chimney" and not h["has_chim"]:
            out.append((lambda e, h=h: setattr(h["chim"], "hide_render", not e),
                        f"a chimney appeared on the {h['wname']} house", f"A CHIMNEY APPEARED ON THE {h['wname'].upper()} HOUSE"))
    if kind == "appear_tree":
        ts = [t for t in T["trees"] if t.get("spot") and onscreen(t["pos"])]
        rng.shuffle(ts)
        for t in ts:
            out.append((lambda e, t=t: hide(t["objs"], not e), "a tree appeared between the houses", "A TREE APPEARED BETWEEN THE HOUSES"))
    return out


# ================================================================= ROOM
ROOM_PAL = [dict(wl=(236, 222, 200), wr=(214, 226, 220), sofa=(70, 112, 128), rug=(196, 92, 74), rug2=(240, 222, 190), floor=(196, 146, 104)),
            dict(wl=(240, 226, 214), wr=(232, 214, 200), sofa=(150, 90, 70), rug=(70, 100, 130), rug2=(236, 228, 210), floor=(178, 132, 96)),
            dict(wl=(222, 230, 214), wr=(240, 236, 222), sofa=(196, 160, 90), rug=(110, 140, 110), rug2=(244, 236, 218), floor=(204, 160, 118)),
            dict(wl=(226, 220, 236), wr=(236, 232, 240), sofa=(96, 90, 130), rug=(220, 150, 110), rug2=(242, 232, 222), floor=(186, 140, 100))]
ART_NAMES = ["coral", "pale blue", "mustard", "mint", "lilac", "teal", "pink"]
CUSH_NAMES = ["mustard", "white", "coral", "teal", "navy", "pink", "sage"]
BOOK_NAMES = ["red", "blue", "yellow", "green", "white", "purple", "orange", "navy"]


def build_room():
    P = rng.choice(ROOM_PAL)
    M = {k: mat(k, c, r, mt) for k, c, r, mt in [
        ("floor", P["floor"], 0.45, 0), ("wallL", P["wl"], 0.85, 0), ("wallR", P["wr"], 0.85, 0), ("base", (250, 248, 242), 0.5, 0),
        ("rug", P["rug"], 0.95, 0), ("rug2", P["rug2"], 0.95, 0), ("sofa", P["sofa"], 0.9, 0), ("wood", (120, 82, 54), 0.5, 0),
        ("wood2", (168, 120, 80), 0.5, 0), ("metal", (40, 40, 44), 0.35, 0.8), ("pot", (226, 112, 76), 0.6, 0),
        ("pot2", (240, 240, 236), 0.4, 0), ("soil", (60, 44, 34), 1.0, 0), ("leaf", (70, 140, 76), 0.5, 0),
        ("leaf2", (96, 160, 80), 0.5, 0), ("stem", (90, 120, 60), 0.6, 0), ("frame", (250, 250, 246), 0.4, 0),
        ("shade", (250, 236, 210), 0.8, 0), ("clockf", (250, 250, 250), 0.3, 0)]}
    R = dict(colors=[], vanish=[], appear=[])
    S = 6.0
    box("floor", (S / 2, S / 2, -0.15), (S + 0.3, S + 0.3, 0.3), M["floor"], 0.04)
    gap = mat("gap", tuple(int(c * 0.76) for c in P["floor"]), 0.6)
    for i in range(13):
        box("board", (S / 2, 0.23 + i * 0.46, 0.002), (S, 0.02, 0.004), gap, 0)
    box("wallL", (-0.15, S / 2, 2.0), (0.3, S + 0.3, 4.3), M["wallL"], 0.04)
    box("wallR", (S / 2, -0.15, 2.0), (S + 0.3, 0.3, 4.3), M["wallR"], 0.04)
    box("skirtL", (0.02, S / 2, 0.08), (0.05, S, 0.16), M["base"], 0.01)
    box("skirtR", (S / 2, 0.02, 0.08), (S, 0.05, 0.16), M["base"], 0.01)
    wy, wz, ww, wh = 3.6, 2.2, 1.8, 1.7
    for (dy, dz, sy, sz) in ((0, wh / 2, ww + 0.16, 0.1), (0, -wh / 2, ww + 0.16, 0.1), (ww / 2, 0, 0.1, wh), (-ww / 2, 0, 0.1, wh),
                             (0, 0, 0.05, wh), (0, 0, ww, 0.05)):
        box("wframe", (0.04, wy + dy, wz + dz), (0.14, sy, sz), M["frame"], 0.01)
    box("sill", (0.12, wy, wz - wh / 2 - 0.08), (0.3, ww + 0.4, 0.06), M["frame"], 0.01)
    bpy.ops.mesh.primitive_cube_add(location=(-0.15, wy, wz)); hole = bpy.context.object
    hole.scale = (0.4, ww / 2, wh / 2); hole.hide_render = True; hole.hide_viewport = True
    bm = bpy.data.objects["wallL"].modifiers.new("hole", "BOOLEAN"); bm.object = hole; bm.operation = "DIFFERENCE"
    cyl("rug", (3.2, 2.8, 0.01), 1.7, 0.02, M["rug"], 64).scale = (1.25, 1.0, 1)
    cyl("rug2", (3.2, 2.8, 0.022), 1.35, 0.02, M["rug2"], 64).scale = (1.25, 1.0, 1)
    sx, sy = 3.3, 0.75
    sofa_nm = min(["teal", "coral", "mustard", "navy", "sage", "lilac"], key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED[n], P["sofa"])))
    set_col(M["sofa"], NAMED[sofa_nm])
    R["colors"].append(("sofa", M["sofa"], sofa_nm, ["teal", "coral", "mustard", "navy", "sage", "lilac", "grey"], "sofa"))
    rug_nm = min(["coral", "blue", "sage", "orange", "teal"], key=lambda n: sum((a - b) ** 2 for a, b in zip(NAMED[n], P["rug"])))
    set_col(M["rug"], NAMED[rug_nm])
    R["colors"].append(("rug", M["rug"], rug_nm, ["coral", "blue", "sage", "orange", "teal", "purple"], "rug"))
    box("sofa_base", (sx, sy, 0.35), (2.8, 1.0, 0.45), M["sofa"], 0.12, segs=3)
    box("sofa_back", (sx, 0.32, 0.85), (2.8, 0.3, 0.9), M["sofa"], 0.13, segs=3)
    for dx in (-1.45, 1.45):
        box("arm", (sx + dx, sy, 0.6), (0.3, 1.0, 0.7), M["sofa"], 0.12, segs=3)
    for dx in (-0.65, 0.65):
        box("seat", (sx + dx, sy + 0.05, 0.64), (1.25, 0.85, 0.18), M["sofa"], 0.08, segs=3)
    cn = rng.sample(CUSH_NAMES, 2)
    for dx, nm in zip((-0.95, 0.95), cn):
        m = mat("cush", NAMED[nm], 0.9)
        o = box("pillow", (sx + dx, 0.62, 0.98), (0.6, 0.18, 0.5), m, 0.09, segs=3); o.rotation_euler.x = -0.2
        R["colors"].append(("cushion", m, nm, CUSH_NAMES, "cushion on the sofa"))
    for dx in (-1.2, 1.2):
        for dy in (0.35, 1.15):
            cyl("leg", (sx + dx, dy, 0.07), 0.04, 0.14, M["wood"], 12)
    box("table", (3.2, 2.9, 0.42), (1.4, 0.8, 0.06), M["wood2"], 0.02)
    for dx in (-0.6, 0.6):
        for dy in (-0.32, 0.32):
            cyl("tleg", (3.2 + dx, 2.9 + dy, 0.2), 0.035, 0.4, M["wood"], 12)
    mug = cyl("mug", (3.5, 3.0, 0.53), 0.08, 0.16, mat("mug", NAMED[rng.choice(["blue", "coral", "mustard", "white"])], 0.3), 24)
    tb = box("tbook", (2.9, 2.85, 0.47), (0.45, 0.32, 0.05), mat("tb", NAMED[rng.choice(BOOK_NAMES)], 0.6), 0.005)
    R["vanish"].append(([mug], "the mug on the table disappeared", "THE MUG ON THE TABLE DISAPPEARED"))
    R["vanish"].append(([tb], "the book on the table disappeared", "THE BOOK ON THE TABLE DISAPPEARED"))
    # bookshelf
    bx, by = 0.28, 1.25
    box("shelf_side", (bx, by - 0.7, 1.3), (0.5, 0.05, 2.6), M["wood"], 0.01)
    box("shelf_side", (bx, by + 0.7, 1.3), (0.5, 0.05, 2.6), M["wood"], 0.01)
    books = []
    for k in range(5):
        box("shelf", (bx, by, 0.05 + k * 0.62), (0.5, 1.45, 0.05), M["wood"], 0.01)
        if k < 4:
            y = by - 0.64
            while y < by + 0.6:
                t = rng.uniform(0.06, 0.12); hgt = rng.uniform(0.34, 0.5)
                if y + t > by + 0.64:
                    break
                nm = rng.choice(BOOK_NAMES); m = mat("bk", NAMED[nm], 0.7)
                o = box("book", (bx + 0.02, y + t / 2, 0.075 + k * 0.62 + hgt / 2), (0.36, t, hgt), m, 0.004)
                if t > 0.1 and 0 < k < 3:
                    books.append((m, nm))
                y += t + 0.006
                if rng.random() < 0.1:
                    y += 0.15
    for m, nm in rng.sample(books, min(3, len(books))):
        R["colors"].append(("book", m, nm, BOOK_NAMES, "book on the shelf"))
    # pictures + clock on the right wall
    an = rng.sample(ART_NAMES, 3)
    for (px, pz, w, h), nm in zip(((2.2, 2.35, 0.95, 1.2), (3.55, 2.5, 1.3, 0.9), (4.75, 2.3, 0.75, 0.75)), an):
        box("pframe", (px, 0.03, pz), (w + 0.1, 0.05, h + 0.1), M["frame"], 0.01)
        m = mat("art", NAMED[nm], 0.8); box("art", (px, 0.06, pz), (w, 0.02, h), m, 0)
        R["colors"].append(("art", m, nm, ART_NAMES, "picture on the wall"))
    clock = [cyl("clock", (5.2, 0.05, 2.9), 0.34, 0.05, M["clockf"], 48, rot=(math.pi / 2, 0, 0)),
             box("hand", (5.2, 0.09, 3.0), (0.025, 0.01, 0.22), M["metal"], 0), box("hand", (5.27, 0.09, 2.9), (0.15, 0.01, 0.025), M["metal"], 0)]
    R["vanish"].append((clock, "the clock on the wall disappeared", "THE CLOCK ON THE WALL DISAPPEARED"))
    lamp = [cyl("lampbase", (5.2, 0.6, 0.03), 0.22, 0.05, M["metal"]), cyl("lamppole", (5.2, 0.6, 0.9), 0.025, 1.8, M["metal"], 12),
            cyl("lampshade", (5.2, 0.6, 1.85), 0.32, 0.4, M["shade"], 32, r2=0.2)]
    R["vanish"].append((lamp, "the floor lamp disappeared", "THE FLOOR LAMP DISAPPEARED"))
    cyl("sidetable", (1.2, 4.6, 0.3), 0.28, 0.6, M["wood2"], 32)
    sill = [cyl("smallpot", (0.14, 3.0, wz - wh / 2), 0.1, 0.16, M["pot2"], 24),
            sphere("succ", (0.14, 3.0, wz - wh / 2 + 0.12), 0.1, M["leaf2"], (1, 1, 0.7))]
    R["vanish"].append((sill, "the small plant on the windowsill disappeared", "THE PLANT ON THE WINDOWSILL DISAPPEARED"))
    # appear candidates (hidden at the start): a vase on the table, a second picture frame, a stack of books on the floor
    vase = [cyl("vase", (2.75, 3.05, 0.58), 0.07, 0.26, mat("vase", NAMED[rng.choice(["teal", "coral", "white"])], 0.3), 24, r2=0.05)]
    R["appear"].append((vase, "a vase appeared on the table", "A VASE APPEARED ON THE TABLE"))
    stack = []
    for i in range(3):
        stack.append(box("stack", (4.9, 3.6, 0.04 + i * 0.07), (0.42, 0.3, 0.065), mat("st", NAMED[rng.choice(BOOK_NAMES)], 0.6), 0.005,
                         rot=(0, 0, rng.uniform(-0.3, 0.3))))
    R["appear"].append((stack, "a stack of books appeared on the floor", "A STACK OF BOOKS APPEARED ON THE FLOOR"))
    frame2 = [box("pframe2", (0.03, 2.3, 2.75), (0.05, 0.5, 0.65), M["frame"], 0.01),
              box("art2", (0.06, 2.3, 2.75), (0.02, 0.4, 0.55), mat("art2", NAMED[rng.choice(ART_NAMES)], 0.8), 0)]
    R["appear"].append((frame2, "a picture appeared on the wall", "A PICTURE APPEARED ON THE WALL"))
    for objs, _, _ in R["appear"]:
        hide(objs, True)
    # plant in the corner
    PX, PY = 1.2, 4.6
    cyl("bigpot", (PX, PY, 0.76), 0.2, 0.32, M["pot"], 32, r2=0.24)
    cyl("soil", (PX, PY, 0.915), 0.22, 0.02, M["soil"], 32)
    for i in range(9):
        ang = i * 2.4 + rng.uniform(-0.2, 0.2); tilt = rng.uniform(0.35, 0.8); L = rng.uniform(0.45, 0.75)
        tip = Vector((math.cos(ang) * math.sin(tilt) * L, math.sin(ang) * math.sin(tilt) * L, math.cos(tilt) * L))
        st = cyl("stem", (PX + tip.x / 2, PY + tip.y / 2, 0.92 + tip.z / 2), 0.012, L, M["stem"], 8)
        st.rotation_euler = tip.to_track_quat("Z", "Y").to_euler()
        lf = sphere("leaf", (PX + tip.x * 1.05, PY + tip.y * 1.05, 0.92 + tip.z * 1.05), 0.2, M["leaf" if rng.random() < 0.6 else "leaf2"], (1.0, 0.62, 0.08))
        lf.rotation_euler = (rng.uniform(0.6, 1.2), 0, ang + math.pi / 2)
    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    bgn = world.node_tree.nodes["Background"]; bgn.inputs[0].default_value = (*srgb((206, 226, 246)), 1); bgn.inputs[1].default_value = 0.6
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(58), 0, math.radians(-80)))
    s = bpy.context.object.data; s.energy = 4.0; s.angle = math.radians(2); s.color = (1.0, 0.88, 0.72)
    bpy.ops.object.light_add(type="AREA", location=(6.5, 7.5, 5.0)); fill = bpy.context.object
    fill.data.energy = 900; fill.data.size = 6; fill.data.color = (0.9, 0.95, 1.0)
    fill.rotation_euler = ((Vector((2.5, 2.5, 1)) - fill.location).to_track_quat("-Z", "Y").to_euler())
    bpy.ops.object.light_add(type="POINT", location=(5.2, 0.6, 1.8)); l = bpy.context.object.data
    l.energy = 25; l.color = (1.0, 0.8, 0.55); l.shadow_soft_size = 0.1
    bpy.ops.object.camera_add(location=(11.5, 11.0, 8.2)); cam = bpy.context.object; sc.camera = cam
    cam.data.lens = 52
    cam.rotation_euler = ((Vector((2.55, 2.4, 1.25)) - cam.location).to_track_quat("-Z", "Y").to_euler())
    sc.render.film_transparent = True
    R["exposure"] = 0.3
    return R


def room_candidates(R, kind):
    out = []
    if kind in ("art", "cushion", "book", "sofa", "rug"):
        cs = [c for c in R["colors"] if c[0] == kind]
        rng.shuffle(cs)
        for _, m, nm, pool, what in cs:
            new = other_name(nm, pool)
            out.append((lambda e, m=m, nm=nm, new=new: set_col(m, NAMED[new if e else nm]),
                        f"the {nm} {what} turned {new}", f"THE {nm.upper()} {what.split(' ')[0].upper()} TURNED {new.upper()}"))
    elif kind == "vanish":
        vs = R["vanish"][:]; rng.shuffle(vs)
        for objs, ans, short in vs:
            out.append((lambda e, objs=objs: hide(objs, e), ans, short))
    elif kind == "appear":
        vs = R["appear"][:]; rng.shuffle(vs)
        for objs, ans, short in vs:
            out.append((lambda e, objs=objs: hide(objs, not e), ans, short))
    return out


def color_candidates(S, kind):
    """generic: S["colors"] = [(kind, material, colour name, pool, label)]"""
    out = []
    cs = [c for c in S["colors"] if c[0] == kind]
    rng.shuffle(cs)
    for _, m, nm, pool, what in cs:
        new = other_name(nm, pool)
        out.append((lambda e, m=m, nm=nm, new=new: set_col(m, NAMED[new if e else nm]),
                    f"the {nm} {what} turned {new}", f"THE {nm.upper()} {what.upper()} TURNED {new.upper()}"))
    return out


def sky_world(top, strength):
    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    bg = world.node_tree.nodes["Background"]; bg.inputs[0].default_value = (*srgb(top), 1); bg.inputs[1].default_value = strength


def sun(rot_deg, energy, col, angle=3):
    bpy.ops.object.light_add(type="SUN", rotation=tuple(math.radians(v) for v in rot_deg))
    s_ = bpy.context.object.data; s_.energy = energy; s_.angle = math.radians(angle); s_.color = col


def look(loc, target, lens):
    bpy.ops.object.camera_add(location=loc); cam = bpy.context.object; sc.camera = cam
    cam.data.lens = lens
    cam.rotation_euler = ((Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler())
    return cam


def gable_house(x, y, w, d, h, wall_m, roof_m, frame_m, glass_m, door_m, z0=0.0, floors=None):
    box("hbody", (x, y, z0 + h / 2), (w, d, h), wall_m, bevel=0.05)
    prism("hroof", (x, y, z0 + h), w, d, 0.5 * d, roof_m)
    fy = y - d / 2
    box("door", (x, fy - 0.03, z0 + 0.55), (0.55, 0.08, 1.1), door_m, bevel=0.02)
    floors = floors or max(1, int(h / 1.2))
    ncol = max(1, int(w / 1.1))
    for f in range(floors):
        wz = z0 + 1.0 + f * (h - 1.0) / floors + 0.45
        for i in range(ncol):
            wx = x - w / 2 + (i + 0.5) * w / ncol
            if f == 0 and abs(wx - x) < 0.45:
                continue
            box("wf", (wx, fy - 0.03, wz), (0.5, 0.06, 0.62), frame_m, bevel=0.01)
            box("wg", (wx, fy - 0.06, wz), (0.38, 0.04, 0.5), glass_m, bevel=0)


# ================================================================= HARBOUR
HULL_NAMES = ["red", "blue", "white", "green", "yellow", "navy", "orange", "turquoise"]
HWALL_NAMES = ["coral", "yellow", "sky blue", "mint", "peach", "lilac", "cream", "turquoise", "pink"]


def build_harbor(mood):
    S = dict(colors=[])
    water = mat("water", (52, 112, 140), 0.08); stone = mat("stone", (176, 168, 156), 0.85)
    frame = mat("frame", (248, 248, 244), 0.5); glass = mat("glass", (50, 70, 96), 0.15); door = mat("door", (96, 70, 52), 0.6)
    wood = mat("wood", (130, 96, 66), 0.7); white = mat("white", (244, 244, 240), 0.5); dark = mat("dark", (44, 48, 56), 0.5)
    box("water", (0, 0, -0.05), (160, 160, 0.1), water, bevel=0)
    box("quay", (0, 9.0, 0.45), (80, 6.0, 1.1), stone, bevel=0.05)
    box("quayedge", (0, 5.95, 1.02), (80, 0.25, 0.12), white, bevel=0.02)
    # harbour houses along the quay: tall, narrow, colourful (original layout)
    x = -20 + rng.uniform(0, 1)
    while x < 20:
        w = rng.uniform(1.9, 2.7); h = rng.uniform(3.6, 5.6); d = 2.6
        wn = rng.choice(HWALL_NAMES); rn = rng.choice(["red", "grey", "brown", "orange"])
        wm = mat("hw", NAMED[wn], 0.75); rm = mat("hr", NAMED[rn], 0.55)
        gable_house(x + w / 2, 10.6, w, d, h, wm, rm, frame, glass, door, z0=1.0)
        S["colors"].append(("hwall", wm, wn, HWALL_NAMES, "house"))
        x += w + rng.uniform(0.05, 0.3)
    # moored boats along the quay (all at the same distance, none in front of the others)
    bx = -15 + rng.uniform(0, 2)
    while bx < 15:
        L = rng.uniform(3.6, 4.6); hn = rng.choice(HULL_NAMES); hm = mat("hull", NAMED[hn], 0.35)
        box("hull", (bx, 4.2, 0.45), (L, 1.7, 1.0), hm, bevel=0.3, segs=3)
        box("deck", (bx, 4.2, 0.98), (L * 0.92, 1.45, 0.06), wood, bevel=0.02)
        if rng.random() < 0.7:
            box("cabin", (bx - L * 0.12, 4.2, 1.3), (L * 0.35, 1.1, 0.6), white, bevel=0.06)
        cyl("mast", (bx + L * 0.1, 4.2, 2.4), 0.04, 3.0, wood, 8)
        S["colors"].append(("hull", hm, hn, HULL_NAMES, "boat"))
        bx += L + rng.uniform(0.4, 1.0)
    # lighthouse on a short pier at the right
    box("pier", (17, 2.0, 0.45), (2.4, 8.0, 1.0), stone, bevel=0.04)
    cyl("lh", (17, -0.8, 3.0), 0.75, 4.2, white, 32, r2=0.55)
    cyl("lhband", (17, -0.8, 2.2), 0.72, 0.6, mat("lhred", (196, 56, 48), 0.5), 32)
    cyl("lhtop", (17, -0.8, 5.4), 0.6, 0.6, glass, 16)
    cyl("lhcap", (17, -0.8, 5.95), 0.7, 0.5, dark, 16, r2=0.1)
    hill = mat("hill", (96, 140, 96), 0.9); hill2 = mat("hill2", (116, 156, 150), 0.9)
    for i in range(10):
        blob("hill", (-55 + i * 12 + rng.uniform(-3, 3), 34 + rng.uniform(0, 10), 0), rng.uniform(10, 16), hill if i % 2 else hill2, 2, rng.uniform(0.5, 0.8))
    if mood == "day":
        sky_world((150, 196, 246), 1.0); sun((52, 8, -30), 2.8, (1.0, 0.94, 0.85))
    else:
        sky_world((248, 176, 140), 0.6); sun((74, 4, -55), 2.4, (1.0, 0.7, 0.45))
    look((rng.uniform(-2, 2), -11.0, 5.0), (0, 8.0, 2.4), 36)
    S["exposure"] = 0.35 if mood == "day" else 0.65
    return S


# ================================================================= FARM
BARN_NAMES = ["red", "white", "sky blue", "olive", "yellow", "grey"]
FIELD_NAMES = ["golden", "lime", "dark green", "brown soil"]


def build_farm(mood):
    S = dict(colors=[])
    grass = mat("grass", (122, 170, 92), 0.9); frame = mat("frame", (248, 248, 244), 0.5); glass = mat("glass", (50, 70, 96), 0.15)
    door = mat("door", (100, 72, 52), 0.6); wood = mat("wood", (150, 112, 76), 0.7); trunk = mat("trunk", (110, 80, 56), 0.8)
    leaf = [mat("leaf", c, 0.8) for c in ((86, 150, 70), (64, 128, 78), (110, 168, 64))]
    box("ground", (0, 0, -0.1), (160, 160, 0.2), grass, bevel=0)
    # patchwork fields behind the farmyard (rows of crops as thin ridges)
    for i in range(4):
        for j in range(2):
            fn = rng.choice(FIELD_NAMES); fm = mat("field", NAMED[fn], 0.95)
            cx, cy = -18 + i * 12 + rng.uniform(-0.5, 0.5), 16 + j * 9
            box("field", (cx, cy, 0.03), (11.2, 8.2, 0.06), fm, bevel=0.05)
            for k in range(9):
                box("ridge", (cx, cy - 3.6 + k * 0.9, 0.08), (10.8, 0.18, 0.08), fm, bevel=0.03)
            S["colors"].append(("field", fm, fn, FIELD_NAMES, "field"))
    # barn + silo + farmhouse
    bn = rng.choice(BARN_NAMES[:3]); bm = mat("barn", NAMED[bn], 0.8); brn = rng.choice(["grey", "white", "brown"])
    brm = mat("barnroof", NAMED[brn], 0.6)
    box("barn", (-3.5, 7.0, 2.2), (6.0, 5.0, 4.4), bm, bevel=0.06)
    prism("barnroof", (-3.5, 7.0, 4.4), 6.0, 5.0, 2.4, brm)
    box("barndoor", (-3.5, 4.47, 1.5), (2.4, 0.08, 3.0), mat("bd", (244, 240, 230), 0.6), bevel=0.02)
    for sgn in (-1, 1):
        o = box("x", (-3.5, 4.38, 1.5), (0.16, 0.05, 3.7), frame, bevel=0.01); o.rotation_euler.y = sgn * 0.68
    S["colors"].append(("barn", bm, bn, BARN_NAMES, "barn"))
    S["colors"].append(("barnroof", brm, brn, ["grey", "white", "brown", "red", "blue", "green"], "barn roof"))
    sn = rng.choice(["white", "grey", "sky blue"]); sm = mat("silo", NAMED[sn], 0.4)
    cyl("silo", (1.6, 8.6, 3.2), 1.1, 6.4, sm, 32); sphere("dome", (1.6, 8.6, 6.4), 1.1, sm, (1, 1, 0.6))
    S["colors"].append(("silo", sm, sn, ["white", "grey", "sky blue", "red", "green", "yellow"], "silo"))
    hn = rng.choice(["cream", "peach", "pale blue", "yellow"]); hm = mat("fh", NAMED[hn], 0.75)
    gable_house(7.5, 7.5, 4.6, 3.6, 3.2, hm, mat("fhr", NAMED[rng.choice(["red", "grey", "brown"])], 0.55), frame, glass, door)
    S["colors"].append(("farmhouse", hm, hn, WALL_NAMES, "farmhouse"))
    # fences, hay bales, trees, tractor
    for x in range(-14, 15, 2):
        cyl("post", (x, 1.5, 0.45), 0.06, 0.9, wood, 8)
    for z in (0.35, 0.7):
        box("rail", (0, 1.5, z), (28, 0.06, 0.08), wood, bevel=0)
    hay = mat("hay", (226, 196, 112), 0.95)
    for i in range(4):
        o = cyl("bale", (-12 + i * 1.6 + rng.uniform(-0.2, 0.2), 6.0 + rng.uniform(-0.6, 0.6), 0.6), 0.6, 1.0, hay, 24)
        o.rotation_euler.x = math.pi / 2
    for i in range(14):
        x = rng.choice([rng.uniform(-24, -9), rng.uniform(11, 24)]); y = rng.uniform(5, 12); sz = rng.uniform(1.3, 2.0)
        cyl("trunk", (x, y, 0.5 * sz), 0.1 * sz, sz, trunk, 8, smooth=False)
        lm = rng.choice(leaf); blob("leaf", (x, y, 1.4 * sz), 0.7 * sz, lm, 1)
    tm = mat("tractor", NAMED[rng.choice(["green", "red", "blue"])], 0.4)
    box("tractor", (4.0, 3.6, 0.9), (1.8, 1.0, 0.8), tm, bevel=0.1); box("cab", (3.6, 3.6, 1.7), (0.9, 0.9, 0.9), glass, bevel=0.06)
    for dx, r in ((-0.5, 0.55), (0.65, 0.35)):
        for dy in (-0.55, 0.55):
            o = cyl("wheel", (4.0 + dx, 3.6 + dy, r), r, 0.25, mat("tyre", (30, 30, 34), 0.7), 20); o.rotation_euler.x = math.pi / 2
    hill = mat("hill", (110, 156, 96), 0.9); hill2 = mat("hill2", (124, 166, 150), 0.9)
    for i in range(10):
        blob("hill", (-60 + i * 13 + rng.uniform(-3, 3), 50 + rng.uniform(0, 10), 0), rng.uniform(12, 18), hill if i % 2 else hill2, 2, rng.uniform(0.45, 0.75))
    if mood == "day":
        sky_world((150, 196, 246), 1.0); sun((50, 10, -35), 2.8, (1.0, 0.94, 0.85))
    else:
        sky_world((248, 176, 140), 0.6); sun((74, 4, -55), 2.4, (1.0, 0.7, 0.45))
    look((rng.uniform(-2, 2), -12.0, 14.0), (0, 13.0, 0.0), 32)
    S["exposure"] = 0.35 if mood == "day" else 0.65
    return S


# ================================================================= render
mood = None
if scene_name == "town":
    mood = rng.choice(["day", "day", "sunset"])
    SCN = build_town(mood); cands = town_candidates(SCN, kind, mood)
elif scene_name == "harbor":
    mood = rng.choice(["day", "day", "sunset"])
    SCN = build_harbor(mood); cands = color_candidates(SCN, kind)
elif scene_name == "farm":
    mood = rng.choice(["day", "day", "sunset"])
    SCN = build_farm(mood); cands = color_candidates(SCN, kind)
else:
    SCN = build_room(); cands = room_candidates(SCN, kind)
cands = [c for c in cands if c[2].upper() not in AVOID and c[1].upper() not in AVOID]
if not cands:
    sys.exit(f"no candidate for {scene_name}/{kind}")

r = sc.render; r.engine = "CYCLES"; r.resolution_x, r.resolution_y = 1000, 900; r.resolution_percentage = 100
sc.cycles.device = "CPU"; sc.cycles.samples = A.samples; sc.cycles.use_denoising = True; sc.cycles.seed = 3
sc.cycles.max_bounces = 6
try:
    sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Punchy"
except Exception:
    try:
        sc.view_settings.view_transform = "Filmic"; sc.view_settings.look = "Medium High Contrast"
    except Exception:
        pass
sc.view_settings.exposure = SCN["exposure"]
r.image_settings.file_format = "PNG"; r.image_settings.color_depth = "16"


def render(path):
    r.filepath = path; bpy.ops.render.render(write_still=True)


def measure(pa, pb):
    ia, ib = bpy.data.images.load(pa), bpy.data.images.load(pb)
    a, b = list(ia.pixels), list(ib.pixels)
    W_, H_ = ia.size
    n = 0; x0 = y0 = 10 ** 9; x1 = y1 = -1
    for i in range(0, len(a), 4):
        d = max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2]), abs(a[i + 3] - b[i + 3]))
        if d > 24 / 255:
            n += 1; p = i // 4; x, y = p % W_, H_ - 1 - p // W_
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    bpy.data.images.remove(ia); bpy.data.images.remove(ib)
    return n / (W_ * H_), [x0, y0, x1, y1]


pa = os.path.join(A.out, "A.png"); pb = os.path.join(A.out, "B.png")
render(pa)  # every candidate starts from the same state
for fn, ans, short in cands[:A.tries]:
    fn(True); render(pb)
    frac, bbox = measure(pa, pb)
    print(f"CG candidate: {short} frac={frac:.4f}")
    if MIN_FRAC <= frac <= MAX_FRAC:
        json.dump(dict(scene=scene_name, mood=mood, kind=kind, change_kind=CHANGE_KIND[kind], answer=ans, short=short,
                       frac=round(frac, 4), box=bbox, seed=A.seed, samples=A.samples),
                  open(os.path.join(A.out, "meta.json"), "w"), indent=1)
        print("CG OK", short); sys.exit(0)
    fn(False)
sys.exit("no candidate within the size limits")
