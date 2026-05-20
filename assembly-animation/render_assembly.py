#!/usr/bin/env python3
"""
Blender Cycles render — Dilder Rev2 Mk2 exploded assembly animation.

Run headless:
  blender --background --python render_assembly.py

Fixes:
  - Parts keep their STL assembly positions (no origin_set mangling)
  - Thumbpiece sits in its cutout, not floating
  - Camera settles to FRONT face (screen-facing) view
  - GPU (HIP) rendering if available, falls back to CPU
"""
import bpy
import math
import os
from mathutils import Vector, Euler

BASE = os.path.dirname(os.path.abspath(__file__))
PARTS_DIR = os.path.join(BASE, "parts")
FRAMES_DIR = os.path.join(BASE, "frames")
os.makedirs(FRAMES_DIR, exist_ok=True)

RES_X, RES_Y = 1280, 720
SAMPLES = 64
FPS = 30

EXPLODED_HOLD   = 30
ASSEMBLY_FRAMES = 180
ASSEMBLED_HOLD  = 30
SETTLE_FRAMES   = 60
FRONT_HOLD      = 90
TOTAL = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD + SETTLE_FRAMES + FRONT_HOLD

# Explode offsets in METERS (model is already scaled to meters)
PARTS_CFG = [
    {"name": "BasePlate",  "file": "BasePlate.stl",  "ez": -0.035, "ex": 0.0,    "ey": 0.0,   "start": 0.0},
    {"name": "AAACradle",  "file": "AAACradle.stl",   "ez":  0.025, "ex": 0.030,  "ey": 0.0,   "start": 0.25},
    {"name": "TopCover",   "file": "TopCover.stl",    "ez":  0.040, "ex": 0.0,    "ey": 0.0,   "start": 0.55},
    {"name": "Thumbpiece", "file": "Thumbpiece.stl",  "ez":  0.045, "ex": -0.020, "ey": 0.0,   "start": 0.8,
     "assembled_offset": (0, 0, -0.010)},  # drop 10mm into TopCover cutout
]

MATS = {
    "BasePlate":  {"color": (0.05, 0.06, 0.15, 1), "rough": 0.15, "trans": 0.25},
    "AAACradle":  {"color": (0.08, 0.10, 0.20, 1), "rough": 0.2, "trans": 0.1},
    "TopCover":   {"color": (0.06, 0.07, 0.18, 1), "rough": 0.1, "trans": 0.5, "alpha": 0.65},
    "Thumbpiece": {"color": (0.55, 0.30, 0.80, 1), "rough": 0.25, "trans": 0.0},
}

# ═══════════════════════════════════════════════════════════════

def setup_render():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    s = bpy.context.scene
    s.render.engine = "CYCLES"

    # GPU (HIP) rendering — RX 9070 XT via ROCm 7.2
    # Only enable discrete GPU; iGPU causes memory faults when used alongside it
    s.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "HIP"
    prefs.refresh_devices()
    for dev in prefs.devices:
        dev.use = "9070" in dev.name
        print(f"  Device: {dev.name} ({dev.type}) — {'ON' if dev.use else 'off'}")
    print("  Using HIP GPU rendering (RX 9070 XT only)")

    s.cycles.samples = SAMPLES
    s.cycles.use_denoising = True
    s.render.resolution_x = RES_X
    s.render.resolution_y = RES_Y
    s.render.film_transparent = True
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGBA"
    s.frame_start = 1
    s.frame_end = TOTAL
    s.render.fps = FPS
    s.view_settings.view_transform = "Filmic"
    s.view_settings.look = "Medium Contrast"

def make_material(name, color, roughness=0.2, transmission=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Subsurface Weight"].default_value = 0.15
    bsdf.inputs["Subsurface Radius"].default_value = (0.01, 0.01, 0.01)
    if transmission > 0:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    return mat

# ═══════════════════════════════════════════════════════════════

def import_parts():
    """Import parts WITHOUT modifying origins. STL vertex positions
    already encode the correct assembly positions from FreeCAD."""
    objs = {}
    for cfg in PARTS_CFG:
        fp = os.path.join(PARTS_DIR, cfg["file"])
        if not os.path.exists(fp):
            continue
        bpy.ops.wm.stl_import(filepath=fp)
        obj = bpy.context.active_object
        obj.name = cfg["name"]
        obj.scale = (0.001, 0.001, 0.001)
        bpy.ops.object.transform_apply(scale=True)
        # DO NOT call origin_set — vertex positions ARE the assembly positions
        objs[cfg["name"]] = obj
        print(f"  {cfg['name']}: dims={obj.dimensions}")
    return objs

def center_with_parent(objs):
    """Center the assembly using a parent empty, keeping part positions intact."""
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in objs.values():
        for v in obj.data.vertices:
            wc = obj.matrix_world @ v.co
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    center = (mins + maxs) / 2
    size = maxs - mins
    print(f"  Assembly center: {center}, size: {size}")

    # Parent empty offsets everything visually without changing part data
    bpy.ops.object.empty_add(location=-center)
    parent = bpy.context.active_object
    parent.name = "AssemblyRoot"
    for obj in objs.values():
        obj.parent = parent

    return size, parent

def apply_materials(objs):
    for name, obj in objs.items():
        cfg = MATS.get(name, {"color": (0.5, 0.5, 0.5, 1), "rough": 0.3})
        mat = make_material(f"mat_{name}", cfg["color"], cfg.get("rough", 0.2),
                            cfg.get("trans", 0.0), cfg.get("alpha", 1.0))
        obj.data.materials.clear()
        obj.data.materials.append(mat)

# ═══════════════════════════════════════════════════════════════

def setup_lights(size):
    d = max(size) * 1.5
    bpy.ops.object.light_add(type="AREA", location=(d, -d * 0.8, d * 1.2))
    key = bpy.context.active_object
    key.data.energy = 10
    key.data.size = d * 1.5
    key.data.color = (1.0, 0.95, 0.88)

    bpy.ops.object.light_add(type="AREA", location=(-d * 0.8, -d * 0.5, d * 0.6))
    fill = bpy.context.active_object
    fill.data.energy = 5
    fill.data.size = d * 2
    fill.data.color = (0.85, 0.9, 1.0)

    bpy.ops.object.light_add(type="AREA", location=(d * 0.3, d, d * 0.4))
    rim = bpy.context.active_object
    rim.data.energy = 8
    rim.data.size = d
    rim.data.color = (0.75, 0.55, 0.95)

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.015, 0.015, 0.025, 1)
    bg.inputs["Strength"].default_value = 0.2

def setup_camera(size):
    d = max(size) * 2.5
    bpy.ops.object.empty_add(location=(0, 0, 0))
    target = bpy.context.active_object
    target.name = "CamTarget"

    bpy.ops.object.camera_add(location=(d, -d, d * 0.7))
    cam = bpy.context.active_object
    cam.name = "Camera"
    bpy.context.scene.camera = cam
    cam.data.lens = 50
    cam.data.clip_start = 0.0001
    cam.data.clip_end = 100

    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    return cam, target, d

# ═══════════════════════════════════════════════════════════════

def animate(objs, cam, orbit_r):
    """Parts animate via obj.location offset (0,0,0 = assembled position)."""
    for cfg in PARTS_CFG:
        obj = objs.get(cfg["name"])
        if not obj:
            continue

        # assembled_offset corrects STL positions that don't match FreeCAD
        ao = cfg.get("assembled_offset", (0, 0, 0))
        assembled = Vector(ao)
        explode = Vector((cfg["ex"], cfg.get("ey", 0), cfg["ez"])) + assembled

        # Frame 1: exploded
        obj.location = explode
        obj.keyframe_insert(data_path="location", frame=1)

        # Hold exploded
        obj.location = explode
        obj.keyframe_insert(data_path="location", frame=EXPLODED_HOLD)

        # Staggered assembly
        a_start = EXPLODED_HOLD + int(cfg["start"] * ASSEMBLY_FRAMES * 0.5)
        a_end = a_start + int(ASSEMBLY_FRAMES * 0.5)
        a_end = min(a_end, EXPLODED_HOLD + ASSEMBLY_FRAMES)

        obj.location = explode
        obj.keyframe_insert(data_path="location", frame=a_start)

        # Return to assembled position (with correction offset)
        obj.location = assembled
        obj.keyframe_insert(data_path="location", frame=a_end)

        obj.location = assembled
        obj.keyframe_insert(data_path="location", frame=TOTAL)

        # Smooth keyframes
        try:
            for fc in obj.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
                    kp.easing = "EASE_IN_OUT"
        except (AttributeError, TypeError):
            pass

    # ── Camera: orbit then settle to FRONT FACE view ──
    orbit_end = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD
    settle_end = orbit_end + SETTLE_FRAMES

    for f in range(1, orbit_end + 1):
        t = (f - 1) / max(orbit_end - 1, 1)
        angle = math.radians(45) + t * math.pi * 1.3
        h = orbit_r * 0.7 * (1 - t * 0.3)
        r = orbit_r * (1 - t * 0.15)
        cam.location = Vector((r * math.cos(angle), r * math.sin(angle), h))
        cam.keyframe_insert(data_path="location", frame=f)

    # Front face = top of device showing screen cutout + thumbstick.
    # Camera elevated above, looking down at ~30° from vertical, slight Y offset for depth
    front_pos = Vector((orbit_r * 0.1, -orbit_r * 0.35, orbit_r * 0.65))
    start_pos = cam.location.copy()
    for f in range(orbit_end, settle_end + 1):
        t = (f - orbit_end) / max(SETTLE_FRAMES, 1)
        t = t * t * (3 - 2 * t)  # smoothstep
        cam.location = start_pos.lerp(front_pos, t)
        cam.keyframe_insert(data_path="location", frame=f)

    for f in range(settle_end, TOTAL + 1):
        cam.location = front_pos
        cam.keyframe_insert(data_path="location", frame=f)

    try:
        for fc in cam.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
    except (AttributeError, TypeError):
        pass

# ═══════════════════════════════════════════════════════════════

def add_screen(objs):
    top = objs.get("TopCover")
    if not top:
        return
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    screen = bpy.context.active_object
    screen.name = "Screen"
    screen.scale = (0.0125, 0.0001, 0.006)
    bpy.ops.object.transform_apply(scale=True)
    screen.location = Vector((top.dimensions.x * 0.5, 0, top.dimensions.z * 0.7))
    screen.parent = top

    mat = bpy.data.materials.new("ScreenMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.92, 0.93, 0.88, 1)
    em.inputs["Strength"].default_value = 0.0
    links.new(em.outputs[0], out.inputs[0])
    screen.data.materials.append(mat)

    appear = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD
    em.inputs["Strength"].default_value = 0.0
    em.inputs["Strength"].keyframe_insert(data_path="default_value", frame=appear)
    em.inputs["Strength"].default_value = 2.0
    em.inputs["Strength"].keyframe_insert(data_path="default_value", frame=appear + 30)

# ═══════════════════════════════════════════════════════════════

def render_frames():
    scene = bpy.context.scene
    for f in range(1, TOTAL + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        if f % 30 == 0 or f == 1:
            print(f"  Frame {f}/{TOTAL}")

def main():
    print("=" * 60)
    print(f"DILDER ASSEMBLY v2 — {TOTAL} frames ({TOTAL / FPS:.1f}s)")
    print("=" * 60)

    setup_render()
    objs = import_parts()
    if not objs:
        print("ERROR: No parts!")
        return

    size, parent = center_with_parent(objs)
    apply_materials(objs)
    setup_lights(size)
    cam, target, orbit_r = setup_camera(size)
    animate(objs, cam, orbit_r)
    add_screen(objs)
    render_frames()

    print(f"\nCompile: ffmpeg -framerate {FPS} -i {FRAMES_DIR}/frame_%04d.png "
          f"-c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p {BASE}/output/assembly.webm")

if __name__ == "__main__":
    main()
