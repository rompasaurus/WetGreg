#!/usr/bin/env python3
"""
Blender Cycles render — Dilder Rev2 Mk2 exploded assembly animation.

Run headless:
  blender --background --python render_assembly.py

Produces PNG frames in ./frames/, compile with:
  ffmpeg -framerate 30 -i frames/frame_%04d.png -c:v libvpx-vp9 -b:v 2M \
    -pix_fmt yuva420p output/assembly.webm
"""
import bpy
import math
import os
from mathutils import Vector, Euler

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
BASE = os.path.dirname(os.path.abspath(__file__))
PARTS_DIR = os.path.join(BASE, "parts")
FRAMES_DIR = os.path.join(BASE, "frames")
os.makedirs(FRAMES_DIR, exist_ok=True)

RES_X, RES_Y = 1280, 720
SAMPLES = 64  # denoiser handles the rest
FPS = 30

# Timing
EXPLODED_HOLD  = 30   # 1s
ASSEMBLY_FRAMES = 180  # 6s
ASSEMBLED_HOLD = 30   # 1s
SETTLE_FRAMES  = 60   # 2s
FRONT_HOLD     = 90   # 3s
TOTAL = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD + SETTLE_FRAMES + FRONT_HOLD

# Parts: explode offsets in MODEL UNITS (meters after 0.001 scale)
PARTS_CFG = [
    {"name": "BasePlate",  "file": "BasePlate.stl",  "ez": -0.035, "ex": 0.0,    "start": 0.0},
    {"name": "AAACradle",  "file": "AAACradle.stl",   "ez":  0.025, "ex": 0.030,  "start": 0.25},
    {"name": "TopCover",   "file": "TopCover.stl",    "ez":  0.040, "ex": 0.0,    "start": 0.55},
    {"name": "Thumbpiece", "file": "Thumbpiece.stl",  "ez":  0.060, "ex": -0.020, "start": 0.8},
]

# ═══════════════════════════════════════════════════════════════
# MATERIALS — translucent 3D-printed resin look
# ═══════════════════════════════════════════════════════════════

def make_material(name, base_color, roughness=0.2, transmission=0.0, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if not bsdf:
        nodes.clear()
        out = nodes.new("ShaderNodeOutputMaterial")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        links.new(bsdf.outputs[0], out.inputs[0])

    bsdf.inputs["Base Color"].default_value = base_color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    # Subsurface for plastic look
    bsdf.inputs["Subsurface Weight"].default_value = 0.15
    bsdf.inputs["Subsurface Radius"].default_value = (0.01, 0.01, 0.01)
    if transmission > 0:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    return mat

MATS = {
    # Dark navy-blue translucent body — boosted saturation for Filmic
    "BasePlate":  {"color": (0.05, 0.06, 0.15, 1), "rough": 0.15, "trans": 0.25},
    "AAACradle":  {"color": (0.08, 0.10, 0.20, 1), "rough": 0.2, "trans": 0.1},
    # Semi-transparent top cover (signature Dilder translucent look)
    "TopCover":   {"color": (0.06, 0.07, 0.18, 1), "rough": 0.1, "trans": 0.5, "alpha": 0.65},
    # Mauve accent thumbpiece
    "Thumbpiece": {"color": (0.55, 0.30, 0.80, 1), "rough": 0.25, "trans": 0.0},
}

# ═══════════════════════════════════════════════════════════════
# SCENE
# ═══════════════════════════════════════════════════════════════

def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
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
    # Use filmic for better dynamic range
    s.view_settings.view_transform = "Filmic"
    s.view_settings.look = "Medium Contrast"

def import_parts():
    objs = {}
    for cfg in PARTS_CFG:
        fp = os.path.join(PARTS_DIR, cfg["file"])
        if not os.path.exists(fp):
            print(f"SKIP: {fp}")
            continue
        bpy.ops.wm.stl_import(filepath=fp)
        obj = bpy.context.active_object
        obj.name = cfg["name"]
        obj.scale = (0.001, 0.001, 0.001)
        bpy.ops.object.transform_apply(scale=True)
        objs[cfg["name"]] = obj
        print(f"  {cfg['name']}: dims={obj.dimensions}")
    return objs

def center_assembly(objs):
    """Move all parts so the assembly is centered at world origin."""
    # Find bounding box center of all parts together
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in objs.values():
        for v in obj.data.vertices:
            world_co = obj.matrix_world @ v.co
            for i in range(3):
                mins[i] = min(mins[i], world_co[i])
                maxs[i] = max(maxs[i], world_co[i])
    center = (mins + maxs) / 2
    print(f"  Assembly center: {center}, size: {maxs - mins}")

    for obj in objs.values():
        obj.location -= center
    # Apply so "home" positions are baked
    for obj in objs.values():
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.transform_apply(location=True)
        obj.select_set(False)

    return maxs - mins  # assembly dimensions

def apply_materials(objs):
    for name, obj in objs.items():
        cfg = MATS.get(name, {"color": (0.5, 0.5, 0.5, 1), "rough": 0.3})
        mat = make_material(
            f"mat_{name}",
            cfg["color"],
            cfg.get("rough", 0.2),
            cfg.get("trans", 0.0),
            cfg.get("alpha", 1.0)
        )
        obj.data.materials.clear()
        obj.data.materials.append(mat)

# ═══════════════════════════════════════════════════════════════
# LIGHTING — 3-point studio setup
# ═══════════════════════════════════════════════════════════════

def setup_lights(size):
    d = max(size) * 1.5  # light distance based on assembly size

    # Key light — warm, from upper-right-front
    bpy.ops.object.light_add(type="AREA", location=(d, -d*0.8, d*1.2))
    key = bpy.context.active_object
    key.name = "Key"
    key.data.energy = 10
    key.data.size = d * 1.5
    key.data.color = (1.0, 0.95, 0.88)
    key.rotation_euler = Euler((math.radians(55), math.radians(10), math.radians(-40)))

    # Fill — cool, from left
    bpy.ops.object.light_add(type="AREA", location=(-d*0.8, -d*0.5, d*0.6))
    fill = bpy.context.active_object
    fill.name = "Fill"
    fill.data.energy = 5
    fill.data.size = d * 2
    fill.data.color = (0.85, 0.90, 1.0)
    fill.rotation_euler = Euler((math.radians(60), 0, math.radians(140)))

    # Rim — mauve accent from behind
    bpy.ops.object.light_add(type="AREA", location=(d*0.3, d, d*0.4))
    rim = bpy.context.active_object
    rim.name = "Rim"
    rim.data.energy = 8
    rim.data.size = d
    rim.data.color = (0.75, 0.55, 0.95)
    rim.rotation_euler = Euler((math.radians(30), 0, math.radians(200)))

    # Environment
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.015, 0.015, 0.025, 1)
    bg.inputs["Strength"].default_value = 0.2

# ═══════════════════════════════════════════════════════════════
# CAMERA
# ═══════════════════════════════════════════════════════════════

def setup_camera(size):
    bpy.ops.object.empty_add(location=(0, 0, 0))
    target = bpy.context.active_object
    target.name = "Target"

    d = max(size) * 2.5
    bpy.ops.object.camera_add(location=(d, -d, d*0.7))
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
# ANIMATION
# ═══════════════════════════════════════════════════════════════

def animate(objs, cam, target, orbit_r):
    # ── Parts: exploded → assembled ──
    for cfg in PARTS_CFG:
        obj = objs.get(cfg["name"])
        if not obj:
            continue
        home = obj.location.copy()
        exploded = home + Vector((cfg["ex"], 0, cfg["ez"]))

        # Frame 1: exploded
        obj.location = exploded
        obj.keyframe_insert(data_path="location", frame=1)

        # Hold exploded
        obj.location = exploded
        obj.keyframe_insert(data_path="location", frame=EXPLODED_HOLD)

        # Staggered assembly start/end
        a_start = EXPLODED_HOLD + int(cfg["start"] * ASSEMBLY_FRAMES * 0.5)
        a_end = a_start + int(ASSEMBLY_FRAMES * 0.5)
        a_end = min(a_end, EXPLODED_HOLD + ASSEMBLY_FRAMES)

        obj.location = exploded
        obj.keyframe_insert(data_path="location", frame=a_start)
        obj.location = home
        obj.keyframe_insert(data_path="location", frame=a_end)

        # Hold assembled
        obj.location = home
        obj.keyframe_insert(data_path="location", frame=TOTAL)

        # Smooth interpolation
        try:
            if obj.animation_data and obj.animation_data.action:
                for fc in obj.animation_data.action.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "BEZIER"
                        kp.easing = "EASE_IN_OUT"
        except AttributeError:
            pass  # Blender 5.x API change

    # ── Camera: slow orbit then settle to front ──
    orbit_end = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD
    settle_end = orbit_end + SETTLE_FRAMES

    for f in range(1, orbit_end + 1):
        t = (f - 1) / max(orbit_end - 1, 1)
        angle = math.radians(45) + t * math.pi * 1.3  # ~235° sweep
        h = orbit_r * 0.7 * (1 - t * 0.3)  # slowly descend
        r = orbit_r * (1 - t * 0.15)  # slowly zoom in
        cam.location = Vector((
            r * math.cos(angle),
            r * math.sin(angle),
            h
        ))
        cam.keyframe_insert(data_path="location", frame=f)

    # Settle to front
    front_pos = Vector((0, -orbit_r * 0.75, orbit_r * 0.12))
    start_pos = cam.location.copy()
    for f in range(orbit_end, settle_end + 1):
        t = (f - orbit_end) / max(SETTLE_FRAMES, 1)
        t = t * t * (3 - 2 * t)  # smoothstep
        cam.location = start_pos.lerp(front_pos, t)
        cam.keyframe_insert(data_path="location", frame=f)

    # Hold front
    for f in range(settle_end, TOTAL + 1):
        cam.location = front_pos
        cam.keyframe_insert(data_path="location", frame=f)

    try:
        if cam.animation_data and cam.animation_data.action:
            for fc in cam.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
    except AttributeError:
        pass

# ═══════════════════════════════════════════════════════════════
# SCREEN — e-ink display on the front face (fades in at end)
# ═══════════════════════════════════════════════════════════════

def add_screen(objs):
    top = objs.get("TopCover")
    if not top:
        return
    # Screen sits on front-facing Y-min surface of TopCover
    # Position: center X of assembly, slightly forward of TopCover center, near top Z
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    screen = bpy.context.active_object
    screen.name = "Screen"
    # E-ink display: ~24.5mm x 12.2mm (250x122 pixels)
    screen.scale = (0.0125, 0.0001, 0.006)
    bpy.ops.object.transform_apply(scale=True)
    # Position: centered, on the front face at the display window
    screen.location = Vector((0, top.dimensions.y * -0.5 - 0.0002, 0.005))
    screen.parent = top
    screen.matrix_parent_inverse = top.matrix_world.inverted()

    # Emissive screen material
    mat = bpy.data.materials.new("ScreenMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.92, 0.93, 0.88, 1)  # warm e-ink white
    em.inputs["Strength"].default_value = 0.0
    links.new(em.outputs[0], out.inputs[0])
    screen.data.materials.append(mat)

    # Fade in during settle + front hold
    appear = EXPLODED_HOLD + ASSEMBLY_FRAMES + ASSEMBLED_HOLD
    em.inputs["Strength"].default_value = 0.0
    em.inputs["Strength"].keyframe_insert(data_path="default_value", frame=appear)
    em.inputs["Strength"].default_value = 3.0
    em.inputs["Strength"].keyframe_insert(data_path="default_value", frame=appear + 30)

# ═══════════════════════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════════════════════

def render_frames():
    scene = bpy.context.scene
    total = TOTAL
    for f in range(1, total + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        if f % 30 == 0 or f == 1:
            print(f"  Frame {f}/{total}")
    print(f"\n  Done! Rendered {total} frames")

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print(f"DILDER ASSEMBLY ANIMATION — {TOTAL} frames ({TOTAL/FPS:.1f}s)")
    print("=" * 60)

    setup()
    objs = import_parts()
    if not objs:
        print("ERROR: No parts!")
        return

    size = center_assembly(objs)
    apply_materials(objs)
    setup_lights(size)
    cam, target, orbit_r = setup_camera(size)
    animate(objs, cam, target, orbit_r)
    add_screen(objs)
    render_frames()

    print(f"\nCompile: ffmpeg -framerate {FPS} -i {FRAMES_DIR}/frame_%04d.png "
          f"-c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p {BASE}/output/assembly.webm")

if __name__ == "__main__":
    main()
