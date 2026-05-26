#!/bin/bash
# PCB showcase: top → flip to back HORIZONTAL → hold → flip to front HORIZONTAL → hold 5s
# 360 frames (12s at 30fps)

PCB="/home/rompasaurus/COdingProjects/Dilder-PCB/Dilder Full PCB Rev 1/Dilder Full PCB Rev 1.kicad_pcb"
OUTDIR="/home/rompasaurus/COdingProjects/WetGreg/assembly-animation/frames/pcb"
export KICAD10_3DMODEL_DIR=/usr/share/kicad/3dmodels

mkdir -p "$OUTDIR"
rm -f "$OUTDIR"/frame_*.png

TOTAL=360
echo "=========================================="
echo "PCB SHOWCASE — $TOTAL frames (12s)"
echo "  Phase 1 (0–1.5s):    Angled top, slow rotate"
echo "  Phase 2 (1.5–3s):    Flip to back + settle horizontal"
echo "  Phase 3 (3–5.5s):    HOLD backside horizontal"
echo "  Phase 4 (5.5–7s):    Flip to front horizontal"
echo "  Phase 5 (7–12s):     HOLD front horizontal (5s)"
echo "=========================================="

for i in $(seq 1 $TOTAL); do
    ANGLES=$(python3 -c "
import math

frame = $i
total = $TOTAL
t = (frame - 1) / (total - 1)  # 0 to 1

# Phase boundaries (as fractions of 12s)
p1 = 1.5 / 12.0    # end of angled top
p2 = 3.0 / 12.0    # end of flip to back
p3 = 5.5 / 12.0    # end of backside hold
p4 = 7.0 / 12.0    # end of flip to front

def smoothstep(v):
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)

if t < p1:
    # Phase 1: Angled top view, gentle Z orbit
    pt = t / p1
    x = -30
    z = pt * 45

elif t < p2:
    # Phase 2: Flip to back + ease Z to 0 for horizontal view
    pt = (t - p1) / (p2 - p1)
    ease = smoothstep(pt)
    x = -30 + ease * (-150)     # -30 → -180
    z = 45 * (1 - ease)         # 45 → 0 (horizontal)

elif t < p3:
    # Phase 3: HOLD backside horizontal
    pt = (t - p2) / (p3 - p2)
    x = -180                    # back view
    z = pt * 5                  # tiny drift

elif t < p4:
    # Phase 4: Flip to front (X: -180 → -360), keep Z near 0
    pt = (t - p3) / (p4 - p3)
    ease = smoothstep(pt)
    x = -180 + ease * (-180)    # -180 → -360 (= 0)
    z = 5 * (1 - ease)          # ease Z back to 0

else:
    # Phase 5: Hold front horizontal (5 seconds)
    x = 0
    z = 0

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
        --width 1920 --height 1200 \
        --quality high \
        --perspective \
        --background transparent \
        --rotate "${X_ROT},0,${Z_ROT}" \
        --floor \
        --zoom 0.85 \
        2>/dev/null

    if [ $((i % 30)) -eq 0 ] || [ $i -eq 1 ]; then
        echo "  Frame $i/$TOTAL (X=${X_ROT} Z=${Z_ROT})"
    fi
done

echo ""
echo "Done! Compile:"
echo "  ffmpeg -framerate 30 -i $OUTDIR/frame_%04d.png -c:v libvpx-vp9 -b:v 2M -pix_fmt yuva420p output/pcb_rotate.webm"
