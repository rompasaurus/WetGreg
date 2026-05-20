#!/usr/bin/env python3
"""Convert 3MF files to binary STL using only stdlib.

3MF is a ZIP containing XML mesh data. This script extracts triangle
meshes and writes binary STL files suitable for Blender import.
"""
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NAMESPACE = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}

def parse_3mf(path):
    """Extract vertices and triangles from a 3MF file."""
    all_verts = []
    all_tris = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith(".model"):
                data = zf.read(name)
                root = ET.fromstring(data)
                for mesh in root.iter("{%s}mesh" % NAMESPACE["m"]):
                    verts_el = mesh.find("m:vertices", NAMESPACE)
                    tris_el = mesh.find("m:triangles", NAMESPACE)
                    if verts_el is None or tris_el is None:
                        continue
                    offset = len(all_verts)
                    for v in verts_el.findall("m:vertex", NAMESPACE):
                        all_verts.append((
                            float(v.get("x")),
                            float(v.get("y")),
                            float(v.get("z"))
                        ))
                    for t in tris_el.findall("m:triangle", NAMESPACE):
                        all_tris.append((
                            int(t.get("v1")) + offset,
                            int(t.get("v2")) + offset,
                            int(t.get("v3")) + offset
                        ))
    return all_verts, all_tris

def cross(a, b):
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0]
    )

def sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])

def normalize(v):
    l = (v[0]**2 + v[1]**2 + v[2]**2) ** 0.5
    if l == 0:
        return (0, 0, 0)
    return (v[0]/l, v[1]/l, v[2]/l)

def write_stl(path, verts, tris):
    """Write a binary STL file."""
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)  # header
        f.write(struct.pack("<I", len(tris)))
        for tri in tris:
            v0, v1, v2 = verts[tri[0]], verts[tri[1]], verts[tri[2]]
            n = normalize(cross(sub(v1, v0), sub(v2, v0)))
            f.write(struct.pack("<fff", *n))
            f.write(struct.pack("<fff", *v0))
            f.write(struct.pack("<fff", *v1))
            f.write(struct.pack("<fff", *v2))
            f.write(struct.pack("<H", 0))  # attribute byte count

def main():
    src_dir = Path("/home/rompasaurus/COdingProjects/Dilder/hardware-design/freecad-mk2")
    out_dir = Path("/home/rompasaurus/COdingProjects/WetGreg/assembly-animation/parts")
    out_dir.mkdir(exist_ok=True)

    # The 3MF exports for the target model
    prefix = "Dilder_Rev2_Mk2 2mm longer line base plate rails for wiring 01-05-2026"
    parts = {
        "BasePlate": src_dir / f"{prefix}-BasePlate.3mf",
        "AAACradle": src_dir / f"{prefix}-AAACradle.3mf",
        "TopCover": src_dir / f"{prefix}-TopCover.3mf",
        "Thumbpiece": src_dir / f"{prefix}-Thumbpiece.3mf",
    }

    for name, path in parts.items():
        if not path.exists():
            print(f"WARNING: {path} not found, skipping")
            continue
        print(f"Converting {name}...")
        verts, tris = parse_3mf(path)
        out_path = out_dir / f"{name}.stl"
        write_stl(out_path, verts, tris)
        print(f"  -> {out_path} ({len(verts)} verts, {len(tris)} tris)")

    print("Done!")

if __name__ == "__main__":
    main()
