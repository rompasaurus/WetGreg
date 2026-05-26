#!/bin/bash
# ══════════════════════════════════════════════════════════════
# Wet Greg — Dilder Assembly & PCB Render Pipeline
# ══════════════════════════════════════════════════════════════
#
# Renders two animations for wetgreg.com:
#   1. Case assembly  — exploded-to-assembled Dilder Rev2 Mk2 (GPU/HIP on RX 9070 XT)
#   2. PCB showcase   — rotating Dilder Full PCB Rev 1        (CPU on Ryzen 9800X3D)
#
# Both renders run in parallel (GPU-bound + CPU-bound).
# Frames are compiled to WebM with alpha transparency via ffmpeg.
#
# Resolution: 1920x1200 @ 30fps, Cycles 64 samples + denoiser
#
# Usage:
#   ./render.sh          — render frames + compile video
#   ./render.sh --compile-only  — skip rendering, just compile existing frames
#
# Output:
#   output/assembly.webm    (390 frames, ~13s)
#   output/pcb_rotate.webm  (240 frames, ~8s)
# ══════════════════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")"

mkdir -p output

compile() {
    echo "=== Compiling assembly.webm ==="
    ffmpeg -y -framerate 30 -i frames/frame_%04d.png \
        -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p \
        output/assembly.webm

    echo "=== Compiling pcb_rotate.webm ==="
    ffmpeg -y -framerate 30 -i frames/pcb/frame_%04d.png \
        -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p \
        output/pcb_rotate.webm
}

if [[ "${1:-}" == "--compile-only" ]]; then
    compile
    echo "=== Done ==="
    exit 0
fi

echo "=== Assembly render (GPU/HIP) ==="
blender --background --python render_assembly.py &
PID_ASSEMBLY=$!

echo "=== PCB render (CPU) ==="
blender --background --python render_pcb_blender.py &
PID_PCB=$!

wait $PID_ASSEMBLY
echo "=== Assembly render complete ==="

wait $PID_PCB
echo "=== PCB render complete ==="

compile

echo "=== All done ==="
