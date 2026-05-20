#!/usr/bin/env python3
"""
Blender Cycles render — PCB rotation showcase with extended backside view.

Run headless (after assembly render finishes):
  blender --background --python render_pcb_blender.py

Phases (8s @ 30fps = 240 frames):
  1. Angled top view, gentle orbit        (0–1.5s,   frames 1–45)
  2. Flip to show back                    (1.5–3s,   frames 46–90)
  3. HOLD backside — screen & joystick    (3–5.5s,   frames 91–165)
  4. Flip back to front                   (5.5–7.5s, frames 166–225)
  5. Hold front view                      (7.5–8s,   frames 226–240)
"""
import bpy
import math
import os
from mathutils import Vector, Euler

BASE = os.path.dirname(os.path.abspath(__file__))
GLB_PATH = os.path.join(BASE, "parts", "pcb_board.glb")
FRAMES_DIR = os.path.join(BASE, "frames", "pcb")
os.makedirs(FRAMES_DIR, exist_ok=True)

RES_X, RES_Y = 1280, 720
SAMPLES = 64
FPS = 30

# Phase frame counts
P1_FRAMES = 45   # angled top orbit
P2_FRAMES = 45   # flip to back
P3_FRAMES = 75   # HOLD backside (2.5s)
P4_FRAMES = 60   # flip to front
P5_FRAMES = 15   # hold front
TOTAL = P1_FRAMES + P2_FRAMES + P3_FRAMES + P4_FRAMES + P5_FRAMES  # 240

# Phase boundaries
P1_END = P1_FRAMES
P2_END = P1_END + P2_FRAMES
P3_END = P2_END + P3_FRAMES
P4_END = P3_END + P4_FRAMES
P5_END = TOTAL


def smoothstep(t):
    """Hermite smoothstep for easing."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def setup_render():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    s = bpy.context.scene
    s.render.engine = "CYCLES"

    # GPU (HIP) — RX 9070 XT via ROCm 7.2
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


def import_pcb():
    """Import the GLB and return the root object + bounding dimensions."""
    bpy.ops.import_scene.gltf(filepath=GLB_PATH)

    # GLB import may create multiple objects — parent them all under an empty
    imported = [o for o in bpy.context.scene.objects if o.type in ('MESH', 'EMPTY')]
    if not imported:
        print("ERROR: No objects imported from GLB!")
        return None, None

    # Compute bounding box of everything
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for obj in imported:
        if obj.type != 'MESH':
            continue
        for v in obj.data.vertices:
            wc = obj.matrix_world @ v.co
            for i in range(3):
                mins[i] = min(mins[i], wc[i])
                maxs[i] = max(maxs[i], wc[i])

    center = (mins + maxs) / 2
    size = maxs - mins
    print(f"  PCB center: {center}, size: {size}")

    # Create a pivot empty at the center and parent everything
    bpy.ops.object.empty_add(location=center)
    pivot = bpy.context.active_object
    pivot.name = "PCB_Pivot"

    for obj in imported:
        if obj.parent is None:
            obj.parent = pivot
            # Compensate so visual position doesn't change
            obj.matrix_parent_inverse = pivot.matrix_world.inverted()

    return pivot, size


def setup_lights(size):
    d = max(size) * 1.5

    # Key light — warm, top-right
    bpy.ops.object.light_add(type="AREA", location=(d, -d * 0.8, d * 1.2))
    key = bpy.context.active_object
    key.data.energy = 15
    key.data.size = d * 1.5
    key.data.color = (1.0, 0.95, 0.88)

    # Fill light — cool, left
    bpy.ops.object.light_add(type="AREA", location=(-d * 0.8, -d * 0.5, d * 0.6))
    fill = bpy.context.active_object
    fill.data.energy = 8
    fill.data.size = d * 2
    fill.data.color = (0.85, 0.9, 1.0)

    # Rim/accent — purple, behind
    bpy.ops.object.light_add(type="AREA", location=(d * 0.3, d, d * 0.4))
    rim = bpy.context.active_object
    rim.data.energy = 10
    rim.data.size = d
    rim.data.color = (0.75, 0.55, 0.95)

    # Backside fill — so the back components are well-lit during the hold
    bpy.ops.object.light_add(type="AREA", location=(0, d * 0.8, -d * 0.3))
    back_fill = bpy.context.active_object
    back_fill.data.energy = 6
    back_fill.data.size = d * 1.5
    back_fill.data.color = (0.9, 0.85, 1.0)

    # Subtle world background
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.015, 0.015, 0.025, 1)
    bg.inputs["Strength"].default_value = 0.3


def setup_camera(size):
    """Fixed camera looking at center. Pull back far enough that the board
    is never clipped at any rotation angle (diagonal is worst case)."""
    # Diagonal of the bounding box = max extent when board rotates edge-on
    diagonal = size.length
    # Pull camera back 3x the diagonal so the board always fits with margin
    d = diagonal * 3.0

    bpy.ops.object.empty_add(location=(0, 0, 0))
    target = bpy.context.active_object
    target.name = "CamTarget"

    bpy.ops.object.camera_add(location=(0, -d, d * 0.2))
    cam = bpy.context.active_object
    cam.name = "Camera"
    bpy.context.scene.camera = cam
    # Use a longer lens to reduce perspective distortion — keeps the whole
    # board visible without fish-eye stretching at the edges
    cam.data.lens = 65
    cam.data.clip_start = 0.0001
    cam.data.clip_end = 200

    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"

    return cam, d


def animate_pcb(pivot):
    """
    Rotate the PCB pivot to showcase all sides.

    KiCad GLB: board lies in XY plane, Z is up/down (thickness).
    Front = -Y face, Back = +Y face.
    We rotate around X axis to flip front/back.
    We add gentle Z rotation for visual interest.
    """
    for frame in range(1, TOTAL + 1):
        if frame <= P1_END:
            # Phase 1: Angled top view, gentle Z orbit
            t = (frame - 1) / max(P1_FRAMES - 1, 1)
            x_rot = math.radians(-20)  # slight tilt showing top
            z_rot = t * math.radians(40)  # gentle orbit

        elif frame <= P2_END:
            # Phase 2: Flip to show back (X rotates from -20 to 180)
            t = (frame - P1_END - 1) / max(P2_FRAMES - 1, 1)
            ease = smoothstep(t)
            x_rot = math.radians(-20 + ease * 200)  # -20 -> 180
            z_rot = math.radians(40 + t * 20)  # slow Z drift

        elif frame <= P3_END:
            # Phase 3: HOLD on backside — dead horizontal back view
            # Slight gentle drift so it's not totally static
            t = (frame - P2_END - 1) / max(P3_FRAMES - 1, 1)
            x_rot = math.radians(180)
            z_rot = math.radians(60 + t * 15)  # very slow drift

        elif frame <= P4_END:
            # Phase 4: Flip back to front (180 -> 360 = 0)
            t = (frame - P3_END - 1) / max(P4_FRAMES - 1, 1)
            ease = smoothstep(t)
            x_rot = math.radians(180 + ease * 180)  # 180 -> 360
            z_rot = math.radians(75 * (1 - ease))  # ease Z back to 0

        else:
            # Phase 5: Hold on front
            x_rot = math.radians(360)  # = 0
            z_rot = 0

        pivot.rotation_euler = Euler((x_rot, 0, z_rot), 'XYZ')
        pivot.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Smooth all keyframes
    if pivot.animation_data and pivot.animation_data.action:
        for fc in pivot.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.easing = 'EASE_IN_OUT'


def render_frames():
    # Clean out old frames first
    import glob
    for old in glob.glob(os.path.join(FRAMES_DIR, "frame_*.png")):
        os.remove(old)

    scene = bpy.context.scene
    for f in range(1, TOTAL + 1):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"frame_{f:04d}.png")
        bpy.ops.render.render(write_still=True)
        if f % 30 == 0 or f == 1:
            print(f"  Frame {f}/{TOTAL}")


def main():
    print("=" * 60)
    print(f"PCB SHOWCASE (Blender Cycles) — {TOTAL} frames ({TOTAL / FPS:.1f}s)")
    print(f"  Phase 1: Angled top orbit         (frames 1–{P1_END})")
    print(f"  Phase 2: Flip to back              (frames {P1_END + 1}–{P2_END})")
    print(f"  Phase 3: HOLD backside             (frames {P2_END + 1}–{P3_END})")
    print(f"  Phase 4: Flip to front             (frames {P3_END + 1}–{P4_END})")
    print(f"  Phase 5: Hold front                (frames {P4_END + 1}–{P5_END})")
    print("=" * 60)

    setup_render()
    pivot, size = import_pcb()
    if not pivot:
        return

    setup_lights(size)
    cam, cam_dist = setup_camera(size)
    animate_pcb(pivot)
    render_frames()

    out_dir = os.path.join(BASE, "output")
    print(f"\nDone! Compile with:")
    print(f"  ffmpeg -framerate {FPS} -i {FRAMES_DIR}/frame_%04d.png "
          f"-c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p {out_dir}/pcb_rotate.webm")


if __name__ == "__main__":
    main()
