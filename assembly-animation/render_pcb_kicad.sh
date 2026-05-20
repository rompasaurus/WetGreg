#!/bin/bash
# PCB showcase: top view → flip to back → flip back to front dead-on
# 180 frames (6s at 30fps) — clean and tight, no unnecessary spinning

PCB="/home/rompasaurus/COdingProjects/Dilder-PCB/Dilder Full PCB Rev 1/Dilder Full PCB Rev 1.kicad_pcb"
OUTDIR="/home/rompasaurus/COdingProjects/WetGreg/assembly-animation/frames/pcb"
export KICAD10_3DMODEL_DIR=/usr/share/kicad/3dmodels

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/frame_*.png

TOTAL=180
echo "=========================================="
echo "PCB SHOWCASE — $TOTAL frames (6s)"
echo "  Phase 1 (0-2s):  Angled top, slow rotate"
echo "  Phase 2 (2-4s):  Flip to show back"
echo "  Phase 3 (4-6s):  Flip back, settle front"
echo "=========================================="

for i in $(seq 1 $TOTAL); do
    ANGLES=$(python3 -c "
import math

frame = $i
total = $TOTAL
t = (frame - 1) / (total - 1)  # 0 to 1

# 3 equal phases
if t < 0.333:
    # Phase 1: Angled top view, gentle Z orbit
    pt = t / 0.333
    x = -30
    z = pt * 60  # 0 to 60 degrees

elif t < 0.667:
    # Phase 2: Flip to show back (X goes from -30 to -180)
    pt = (t - 0.333) / 0.334
    ease = pt * pt * (3 - 2 * pt)
    x = -30 + ease * (-150)  # -30 to -180
    z = 60 + pt * 30  # continue rotating slowly

else:
    # Phase 3: Flip back to front (X goes from -180 to -360 = 0)
    pt = (t - 0.667) / 0.333
    ease = pt * pt * (3 - 2 * pt)
    x = -180 + ease * (-180)  # -180 to -360 (= 0)
    z = 90 * (1 - ease)  # ease Z back to 0

# Normalize
x = x % 360
if x > 180:
    x = x - 360

print(f'{round(x,1)},{round(z % 360, 1)}')
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
        echo "  Frame $i/$TOTAL (X=${X_ROT} Z=${Z_ROT})"
    fi
done

echo ""
echo "Done! Compile:"
echo "  ffmpeg -framerate 30 -i $OUTDIR/frame_%04d.png -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p output/pcb_rotate.webm"
