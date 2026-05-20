#!/bin/bash
# Render PCB showcase: tumble rotation showing ALL sides, settle to front dead-on
# 300 frames (10s at 30fps)
#
# Animation path:
#   Phase 1 (frames 1-90, 3s):    3/4 orbit, top angled view
#   Phase 2 (frames 91-150, 2s):  Tilt to show the BACK side (flip over)
#   Phase 3 (frames 151-210, 2s): Come back around, showing bottom-side angles
#   Phase 4 (frames 211-270, 2s): Return to top, slow down rotation
#   Phase 5 (frames 271-300, 1s): Settle to dead-on front top view

PCB="/home/rompasaurus/COdingProjects/Dilder-PCB/Dilder Full PCB Rev 1/Dilder Full PCB Rev 1.kicad_pcb"
OUTDIR="/home/rompasaurus/COdingProjects/WetGreg/assembly-animation/frames/pcb"
export KICAD10_3DMODEL_DIR=/usr/share/kicad/3dmodels

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/frame_*.png

TOTAL=300
echo "=========================================="
echo "PCB SHOWCASE RENDER — $TOTAL frames (10s)"
echo "=========================================="

for i in $(seq 1 $TOTAL); do
    # Python does the math for smooth animation curves
    ANGLES=$(python3 -c "
import math

frame = $i
total = $TOTAL

t = (frame - 1) / (total - 1)  # 0 to 1

# Z rotation: full 540° sweep (1.5 rotations), decelerating at end
if t < 0.9:
    # Main rotation phase
    zt = t / 0.9
    z = zt * 540
else:
    # Settle phase: ease to 0° (front view)
    st = (t - 0.9) / 0.1
    ease = st * st * (3 - 2 * st)  # smoothstep
    z_at_90 = 540.0
    z = z_at_90 * (1 - ease)  # ease to 0

# X rotation (tilt): shows all angles
# Start at -30 (angled top), dip to -180 (back side), return to 0 (dead-on)
if t < 0.25:
    # Angled top view
    x = -30 + t * 4 * (-10)  # -30 to -40
elif t < 0.5:
    # Flip to show back: -40 to -180
    ft = (t - 0.25) / 0.25
    ease = ft * ft * (3 - 2 * ft)
    x = -40 + ease * (-140)  # -40 to -180
elif t < 0.75:
    # Come back from back: -180 to -320 (same as -320 + 360 = +40)
    ft = (t - 0.5) / 0.25
    ease = ft * ft * (3 - 2 * ft)
    x = -180 + ease * (-140)  # -180 to -320
elif t < 0.9:
    # Settling: -320 to -360 (= 0°)
    ft = (t - 0.75) / 0.15
    ease = ft * ft * (3 - 2 * ft)
    x = -320 + ease * (-40)  # -320 to -360
else:
    # Final settle to dead-on: just 0 (or -360 same thing)
    st = (t - 0.9) / 0.1
    ease = st * st * (3 - 2 * st)
    x = -360 + ease * 25  # slight -335 → nice ~-25° presentation angle
    x = -25 * (1 - ease)  # ease from -25 to 0

# Normalize
x = x % 360
if x > 180:
    x = x - 360
z = z % 360

print(f'{round(x,1)},{round(z,1)}')
")

    X_ROT=$(echo "$ANGLES" | cut -d',' -f1)
    Z_ROT=$(echo "$ANGLES" | cut -d',' -f2)

    PADDED=$(printf "%04d" $i)
    OUTFILE="$OUTDIR/frame_${PADDED}.png"

    kicad-cli pcb render "$PCB" \
        -o "$OUTFILE" \
        --width 1280 --height 720 \
        --quality high \
        --perspective \
        --background transparent \
        --rotate "${X_ROT},0,${Z_ROT}" \
        --floor \
        --zoom 1.1 \
        2>/dev/null

    if [ $((i % 30)) -eq 0 ] || [ $i -eq 1 ]; then
        echo "  Frame $i/$TOTAL (X=${X_ROT}° Z=${Z_ROT}°)"
    fi
done

echo ""
echo "Done! $TOTAL frames in $OUTDIR"
echo "Compile: ffmpeg -framerate 30 -i $OUTDIR/frame_%04d.png -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p output/pcb_rotate.webm"
