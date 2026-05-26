#!/usr/bin/env python3
"""
Blender Cycles render — Dilder Full PCB Rev 1 rotating showcase.

Run headless:
  blender --background --python render_pcb.py

Produces PNG frames in ./frames/pcb/, compile with:
  ffmpeg -framerate 30 -i frames/pcb/frame_%04d.png -c:v libvpx-vp9 \
    -b:v 2M -pix_fmt yuva420p output/pcb_rotate.webm
"""
import bpy
import math
import os
from mathutils import Vector, Euler

BASE = os.path.dirname(os.path.abspath(__file__))
PCB_FILE = os.path.join(BASE, "parts", "pcb_full.glb")
FRAMES_DIR = os.path.join(BASE, "frames", "pcb")
os.makedirs(FRAMES_DIR, exist_ok=True)

RES_X, RES_Y = 1920, 1200
SAMPLES = 64
FPS = 30
DURATION = 8  # seconds for full rotation
TOTAL = FPS * DURATION  # 240 frames

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
    s.view_settings.view_transform = "Filmic"
    s.view_settings.look = "Medium Contrast"

def import_pcb():
    bpy.ops.import_scene.gltf(filepath=PCB_FILE)
    # Group all imported objects under an empty for rotation
    imported = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    print(f"Imported {len(imported)} mesh objects from GLB")

    # Create parent empty
    bpy.ops.object.empty_add(location=(0, 0, 0))
    parent = bpy.context.active_object
    parent.name = "PCB_Root"

    # Find bounding box center
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in imported:
        for v in obj.data.vertices:
            wc = obj.matrix_world @ v.co
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])
    center = (mins + maxs) / 2
    size = maxs - mins
    print(f"PCB center: {center}, size: {size}")

    # Parent all meshes and center
    for obj in imported:
        obj.parent = parent
    parent.location = -center

    return parent, size

def setup_lights(size):
    d = max(size) * 2.0

    # Key — warm white from top-right
    bpy.ops.object.light_add(type="AREA", location=(d, -d*0.6, d*1.5))
    key = bpy.context.active_object
    key.data.energy = 12
    key.data.size = d * 2
    key.data.color = (1.0, 0.96, 0.9)
    key.rotation_euler = Euler((math.radians(50), 0, math.radians(-30)))

    # Fill — cool from left-below
    bpy.ops.object.light_add(type="AREA", location=(-d, -d*0.3, d*0.3))
    fill = bpy.context.active_object
    fill.data.energy = 4
    fill.data.size = d * 2
    fill.data.color = (0.88, 0.92, 1.0)

    # Rim — mauve from behind
    bpy.ops.object.light_add(type="AREA", location=(0, d, d*0.5))
    rim = bpy.context.active_object
    rim.data.energy = 6
    rim.data.size = d
    rim.data.color = (0.75, 0.55, 0.95)

    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.01, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.15

def setup_camera(size):
    d = max(size) * 2.5
    bpy.ops.object.camera_add(location=(d*0.8, -d*0.8, d*0.5))
    cam = bpy.context.active_object
    cam.name = "Camera"
    bpy.context.scene.camera = cam
    cam.data.lens = 50
    cam.data.clip_start = 0.0001
    cam.data.clip_end = 100

    # Track to origin
    bpy.ops.object.empty_add(location=(0, 0, 0))
    tgt = bpy.context.active_object
    tgt.name = "CamTarget"
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    return cam

def animate_rotation(pcb_root):
    """Smooth 360° rotation with slight tilt."""
    for f in range(1, TOTAL + 1):
        t = (f - 1) / TOTAL
        # Full 360 rotation around Z
        angle_z = t * math.pi * 2
        # Gentle rock on X (±10°)
        angle_x = math.radians(15) + math.sin(t * math.pi * 2) * math.radians(10)
        pcb_root.rotation_euler = Euler((angle_x, 0, angle_z))
        pcb_root.keyframe_insert(data_path="rotation_euler", frame=f)

    try:
        if pcb_root.animation_data and pcb_root.animation_data.action:
            for fc in pcb_root.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "BEZIER"
    except AttributeError:
        pass

def render_frames():
    scene = bpy.context.scene
    for f in range(1, TOTAL + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        if f % 30 == 0 or f == 1:
            print(f"  Frame {f}/{TOTAL}")
    print(f"\n  Done! {TOTAL} frames rendered")

def main():
    print("=" * 60)
    print(f"DILDER PCB ROTATING RENDER — {TOTAL} frames ({DURATION}s)")
    print("=" * 60)

    setup()
    pcb_root, size = import_pcb()
    setup_lights(size)
    setup_camera(size)
    animate_rotation(pcb_root)
    render_frames()

    print(f"\nCompile: ffmpeg -framerate {FPS} -i {FRAMES_DIR}/frame_%04d.png "
          f"-c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p {BASE}/output/pcb_rotate.webm")

if __name__ == "__main__":
    main()
