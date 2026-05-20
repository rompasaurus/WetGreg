# Dilder Assembly & PCB Animation Pipeline

How the ray-traced 3D animations on wetgreg.com were created.

## Overview

Two animations are rendered for the Wet Greg intro page:

1. **Assembly Animation** — Exploded-to-assembled view of the Dilder Rev2 Mk2 case, with slow camera orbit settling to the front screen view.
2. **PCB Rotation** — Smooth 360° rotating showcase of the Dilder Full PCB Rev 1 with all components.

Both are rendered using **Blender Cycles** (CPU ray tracing) and compiled to WebM video with **FFmpeg**.

## Source Assets

### Case Parts (Assembly Animation)
- **Source model**: `Dilder_Rev2_Mk2 2mm longer line base plate rails for wiring 01-05-2026.FCStd`
- **Location**: `/home/rompasaurus/COdingProjects/Dilder/hardware-design/freecad-mk2/`
- **Parts exported**: 4 individual 3MF files (BasePlate, AAACradle, TopCover, Thumbpiece)
- **Conversion**: 3MF → STL via `convert_3mf_to_stl.py` (stdlib-only, no dependencies)

### PCB (Rotation Animation)
- **Source design**: `Dilder Full PCB Rev 1.kicad_pcb`
- **Location**: `/home/rompasaurus/COdingProjects/Dilder-PCB/Dilder Full PCB Rev 1/`
- **Export**: KiCad CLI → GLB (binary glTF) with tracks, pads, zones, silkscreen, and solder mask
- **Command**: `kicad-cli pcb export glb "Dilder Full PCB Rev 1.kicad_pcb" -o pcb_full.glb --include-tracks --include-pads --include-zones --include-silkscreen --include-soldermask --subst-models`

## Tools

| Tool | Version | Purpose |
|------|---------|---------|
| FreeCAD | — | Original case CAD modeling |
| KiCad | 10.0.2 | PCB design + 3D export |
| Blender | 5.1.1 | Cycles ray-traced rendering |
| FFmpeg | n8.1.1 | Frame-to-video compilation |
| Python 3 | 3.x | Conversion scripts |

## Pipeline

### Step 1: Export Parts

```bash
# Case parts: 3MF → STL
python3 convert_3mf_to_stl.py

# PCB: KiCad → GLB
kicad-cli pcb export glb "Dilder Full PCB Rev 1.kicad_pcb" \
  -o parts/pcb_full.glb \
  --include-tracks --include-pads --include-zones \
  --include-silkscreen --include-soldermask --subst-models
```

### Step 2: Render Frames

```bash
# Assembly animation (390 frames, ~13s at 30fps)
blender --background --python render_assembly.py

# PCB rotation (240 frames, ~8s at 30fps)
blender --background --python render_pcb.py
```

### Step 3: Compile Video

```bash
# Assembly → WebM with alpha transparency
ffmpeg -framerate 30 -i frames/frame_%04d.png \
  -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p \
  output/assembly.webm

# PCB → WebM with alpha transparency
ffmpeg -framerate 30 -i frames/pcb/frame_%04d.png \
  -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p \
  output/pcb_rotate.webm
```

## Render Settings

### Assembly Animation (`render_assembly.py`)
- **Resolution**: 1280x720
- **Engine**: Cycles CPU
- **Samples**: 64 + denoiser
- **Tonemapping**: Filmic, Medium Contrast
- **Background**: Transparent (RGBA PNG)
- **Lighting**: 3-point studio (warm key, cool fill, mauve rim accent)
- **Materials**: Subsurface-scattered plastic with transmission (translucent top cover)
- **Camera**: Orbiting 3/4 view → settles to front screen view
- **Duration**: 13s (1s exploded hold, 6s assembly, 1s hold, 2s settle, 3s front)
- **Parts**: BasePlate, AAACradle, TopCover, Thumbpiece (staggered assembly timing)

### PCB Rotation (`render_pcb.py`)
- **Resolution**: 1280x720
- **Engine**: Cycles CPU
- **Samples**: 64 + denoiser
- **Background**: Transparent
- **Lighting**: 3-point studio matching assembly style
- **Camera**: Fixed position, PCB rotates 360° with gentle X-axis rock
- **Duration**: 8s (full rotation at 30fps)
- **Source**: 52 mesh objects from KiCad GLB export (board + all components)

## File Structure

```
assembly-animation/
├── HOW-IT-WAS-MADE.md          # This file
├── convert_3mf_to_stl.py       # 3MF → STL converter
├── render_assembly.py           # Blender assembly animation script
├── render_pcb.py                # Blender PCB rotation script
├── parts/                       # Source mesh files
│   ├── BasePlate.stl
│   ├── AAACradle.stl
│   ├── TopCover.stl
│   ├── Thumbpiece.stl
│   ├── pcb_full.glb
│   └── pcb_full.step
├── frames/                      # Rendered PNG frames
│   ├── frame_0001.png ... frame_0390.png
│   └── pcb/
│       └── frame_0001.png ... frame_0240.png
└── output/                      # Final compiled videos
    ├── assembly.webm
    └── pcb_rotate.webm
```

## Color Palette

Materials use the **Catppuccin Mocha** palette to match wetgreg.com:
- Body/case: Deep navy `(0.05, 0.06, 0.15)`
- Top cover: Translucent navy with 50% transmission
- Thumbpiece: Mauve accent `(0.55, 0.30, 0.80)`
- Rim light: Mauve `(0.75, 0.55, 0.95)`
- Environment: Near-black `(0.01, 0.01, 0.02)`
