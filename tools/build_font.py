#!/usr/bin/env python3
"""Build BanglaCells: one pre-shaped, cell-sized glyph per Bangla grapheme cluster.

HarfBuzz shapes every cluster with a real Bangla font (GSUB conjuncts, vowel
reordering, GPOS mark placement). The shaped result is flattened into a single
outline, fitted into one terminal cell, and stored in Supplementary Private Use
Area-B (U+100000+), which Nerd Fonts do not use. The Neovim plugin in
lua/bangla_cells conceals each cluster with its private codepoint.

Outputs:
  build/BanglaCells.ttf          standalone font (or a patched copy of --mono with --merge)
  lua/bangla_cells/map.lua       cluster -> codepoint table for the plugin
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import flagOverlapSimple

sys.path.insert(0, str(Path(__file__).parent))
from clusters import builtin_clusters  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "lua" / "bangla_cells" / "map.lua"
PUA_START = 0x100000
PUA_END = 0x10FFFD
DEFAULT_FONT = Path.home() / "Library/Fonts/NotoSansBengali-VariableFont.ttf"
DEFAULT_MISSING = Path.home() / ".local/state/nvim/bangla_cells_missing.txt"
BENGALI = re.compile(r"[ঀ-৿]")


def nvim_segment(lines):
    """Return Neovim's grapheme clusters for each line."""
    seg = Path(__file__).parent / "segment.lua"
    env = {k: v for k, v in os.environ.items() if k != "NVIM_LISTEN_ADDRESS"}
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp, "in.txt"), Path(tmp, "out.txt")
        src.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.run(["nvim", "--clean", "--headless", "-l", str(seg), str(src), str(dst)],
                       check=True, env=env)
        rows = dst.read_text(encoding="utf-8").split("\n")[:len(lines)]
    return [r.split("\t") if r else [] for r in rows]


def corpus_clusters(paths):
    lines = []
    for p in map(Path, paths):
        files = [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else [p]
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lines += [l.replace("\t", " ") for l in text.splitlines() if BENGALI.search(l)]
    found = set()
    for row in nvim_segment(lines) if lines else []:
        found.update(c for c in row if BENGALI.search(c))
    return sorted(found)


def read_existing_map():
    if not MAP_PATH.exists():
        return {}
    pat = re.compile(r'^\["(.*)"\]=0x([0-9A-F]+),$')
    out = {}
    for line in MAP_PATH.read_text(encoding="utf-8").splitlines():
        m = pat.match(line)
        if m:
            out[m.group(1)] = int(m.group(2), 16)
    return out


def shape_all(font_path, clusters, variations):
    """Shape every cluster with hb-shape; returns a list of glyph runs."""
    cmd = ["hb-shape", "--output-format=json", "--no-glyph-names",
           "--script=beng", "--language=bn", str(font_path)]
    if variations:
        cmd.insert(1, "--variations=" + ",".join(f"{k}={v}" for k, v in variations.items()))
    res = subprocess.run(cmd, input="\n".join(clusters) + "\n", capture_output=True,
                         text=True, check=True)
    runs = [json.loads(l) for l in res.stdout.splitlines() if l.strip()]
    if len(runs) != len(clusters):
        sys.exit(f"hb-shape returned {len(runs)} runs for {len(clusters)} clusters")
    return runs


def flatten(run, glyphset, order):
    """Draw a shaped run into one recording pen (components decomposed); returns (pen, bounds) or None."""
    if any(g["g"] == 0 for g in run):
        return None                                   # .notdef: font can't draw it
    rec = DecomposingRecordingPen(glyphset)
    x = 0
    for g in run:
        glyphset[order[g["g"]]].draw(TransformPen(rec, (1, 0, 0, 1, x + g["dx"], g["dy"])))
        x += g["ax"]
    bp = BoundsPen(None)
    rec.replay(bp)
    if bp.bounds is None:
        return None
    return rec, bp.bounds


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * q))]


def load_mono(args):
    """Open --mono; a variable font is pinned to a static instance first."""
    f = TTFont(args.mono, fontNumber=args.mono_index)
    if "fvar" in f:
        from fontTools.varLib.instancer import instantiateVariableFont
        axes = {a.axisTag: a.defaultValue for a in f["fvar"].axes}
        if "wght" in axes:
            axes["wght"] = args.mono_wght
        f = instantiateVariableFont(f, axes)
    return f


def target_metrics(args):
    if not args.mono:
        return dict(upm=1000, advance=600, ascent=880, descent=-240)
    f = load_mono(args)
    cmap = f.getBestCmap()
    adv = f["hmtx"][cmap[ord("M")]][0]
    return dict(upm=f["head"].unitsPerEm, advance=adv,
                ascent=f["hhea"].ascent, descent=f["hhea"].descent)


def build_glyphs(shaped, src_upm, m, pad):
    """Fit each flattened cluster into one cell. Returns {cluster: TTGlyph}."""
    unit = m["upm"] / src_upm
    asc, desc = m["ascent"], m["descent"]
    # One vertical scale and shift for everything so the text keeps an even
    # height: Bangla's full span (matra loops to ু/ৃ) is centred in the cell
    # instead of hanging off the Latin baseline, which would shrink it a lot.
    top = percentile([b[3] for _, b in shaped.values()], 0.99)
    bot = -percentile([-b[1] for _, b in shaped.values()], 0.99)
    sy = unit * min(1.0, (asc - desc) / ((top - bot) * unit))
    shift = (asc + desc) / 2 - sy * (top + bot) / 2
    avail = m["advance"] * (1 - 2 * pad)

    out = {}
    for cluster, (rec, (x0, y0, x1, y1)) in shaped.items():
        # Shrink outliers that are taller or deeper than the cell.
        k = min(1.0, (asc - shift) / max(y1 * sy, 1), (shift - desc) / max(-y0 * sy, 1))
        ys = sy * k
        xs = min(ys, avail / max(x1 - x0, 1))          # condense, never stretch
        dx = (m["advance"] - (x1 - x0) * xs) / 2 - x0 * xs
        pen = TTGlyphPen(None)
        rec.replay(TransformPen(pen, (xs, 0, 0, ys, dx, shift)))
        g = pen.glyph()
        if g.numberOfContours > 0:
            g.flags[0] |= flagOverlapSimple
            g.recalcBounds(None)
        out[cluster] = g
    return out


def assign_codepoints(clusters, existing):
    used = set(existing.values())
    nxt = max(used, default=PUA_START - 1) + 1
    cps = {}
    for c in clusters:
        if c in existing:
            cps[c] = existing[c]
        else:
            while nxt in used:
                nxt += 1
            if nxt > PUA_END:
                sys.exit("ran out of private-use codepoints")
            cps[c] = nxt
            used.add(nxt)
    return cps


def write_standalone(path, glyphs, cps, m):
    names = {c: f"bc{cps[c]:06X}" for c in glyphs}
    order = [".notdef", "space"] + sorted(names.values())
    fb = FontBuilder(m["upm"], isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x20: "space", **{cps[c]: names[c] for c in glyphs}})
    empty = TTGlyphPen(None).glyph()
    gl = {".notdef": empty, "space": empty, **{names[c]: g for c, g in glyphs.items()}}
    fb.setupGlyf(gl)
    fb.setupHorizontalMetrics({n: (m["advance"], getattr(gl[n], "xMin", 0)) for n in order})
    fb.setupHorizontalHeader(ascent=m["ascent"], descent=m["descent"])
    fb.setupNameTable({"familyName": "BanglaCells", "styleName": "Regular",
                       "psName": "BanglaCells-Regular", "version": "Version 1.0"})
    fb.setupOS2(sTypoAscender=m["ascent"], sTypoDescender=m["descent"], sTypoLineGap=0,
                usWinAscent=m["ascent"], usWinDescent=-m["descent"], achVendID="NONE",
                panose=_mono_panose())
    fb.setupPost(isFixedPitch=1)
    fb.save(path)


def _mono_panose():
    from fontTools.ttLib.tables.O_S_2f_2 import Panose
    p = Panose()
    p.bFamilyType, p.bProportion = 2, 9
    return p


def write_merged(path, args, glyphs, cps, m):
    f = load_mono(args)
    if "glyf" not in f:
        sys.exit("--merge needs a TrueType (glyf) font, not CFF/OTF outlines")
    order = f.getGlyphOrder()
    taken = set(order)
    names = {c: f"bc{cps[c]:06X}" for c in glyphs}
    assert not taken & set(names.values())
    new_order = order + sorted(names.values())
    if len(new_order) > 65535:
        sys.exit("too many glyphs for one font; build fewer clusters")

    glyf, hmtx = f["glyf"], f["hmtx"]
    for c, g in glyphs.items():
        glyf.glyphs[names[c]] = g
        hmtx.metrics[names[c]] = (m["advance"], getattr(g, "xMin", 0))
    f.setGlyphOrder(new_order)
    glyf.glyphOrder = new_order
    for tag in ("hdmx", "LTSH", "VDMX", "DSIG"):   # per-glyph tables we can't extend
        if tag in f:
            del f[tag]

    mapping = dict(f.getBestCmap())
    mapping.update({cps[c]: names[c] for c in glyphs})
    cmap = f["cmap"]
    cmap.tables = [t for t in cmap.tables if t.format != 12]
    for pid, eid in ((0, 4), (3, 10)):
        t = CmapSubtable.newSubtable(12)
        t.platformID, t.platEncID, t.language, t.cmap = pid, eid, 0, dict(mapping)
        cmap.tables.append(t)

    family = f["name"].getBestFamilyName()
    new_family = f"{family} Bangla"
    style = f["name"].getBestSubFamilyName() or "Regular"
    for rec in f["name"].names:
        if rec.nameID in (1, 16):
            rec.string = new_family
        elif rec.nameID == 4:
            rec.string = f"{new_family} {style}"
        elif rec.nameID in (3, 6):
            rec.string = f"{new_family}-{style}".replace(" ", "")
    f.save(path)
    return new_family


def write_map(cps, args, m):
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["-- Generated by tools/build_font.py. Do not edit; rebuild instead.",
             f"-- font: {Path(args.font).name}  cell: {m['advance']}/{m['upm']}",
             "return {"]
    lines += [f'["{c}"]=0x{cp:06X},' for c, cp in sorted(cps.items(), key=lambda kv: kv[1])]
    lines.append("}")
    MAP_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--font", default=str(DEFAULT_FONT), help="Bangla source font")
    ap.add_argument("--wdth", type=float, default=62.5,
                    help="width axis of a variable source font (62.5 = condensed)")
    ap.add_argument("--wght", type=float, default=400, help="weight axis of a variable source font")
    ap.add_argument("--mono", help="your terminal font; glyphs are sized to its cell")
    ap.add_argument("--mono-index", type=int, default=0, help="face index inside a .ttc")
    ap.add_argument("--mono-wght", type=float, default=400,
                    help="weight to pin a variable --mono font at")
    ap.add_argument("--merge", action="store_true",
                    help="write a patched copy of --mono that contains the Bangla glyphs")
    ap.add_argument("--corpus", nargs="*", default=[],
                    help="text files/dirs to harvest extra clusters from")
    ap.add_argument("--extra", nargs="*", default=[],
                    help="files with one cluster per line (default: the plugin's missing log)")
    ap.add_argument("--pad", type=float, default=0.03, help="horizontal padding per side (fraction)")
    ap.add_argument("--out-dir", default=str(ROOT / "build"))
    ap.add_argument("--install", action="store_true", help="copy the font to ~/Library/Fonts")
    args = ap.parse_args()

    if args.merge and not args.mono:
        ap.error("--merge requires --mono")
    for tool in ("hb-shape", "nvim"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found on PATH")

    src = TTFont(args.font)
    variations = {}
    if "fvar" in src:
        axes = {a.axisTag for a in src["fvar"].axes}
        variations = {k: v for k, v in (("wdth", args.wdth), ("wght", args.wght)) if k in axes}

    extra_files = args.extra or ([str(DEFAULT_MISSING)] if DEFAULT_MISSING.exists() else [])
    extra = [l.strip("\n") for f in extra_files
             for l in Path(f).read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = read_existing_map()
    candidates = list(dict.fromkeys(builtin_clusters() + corpus_clusters(args.corpus)
                                    + extra + list(existing)))

    # Keep only strings that Neovim draws as exactly one cell.
    clusters = [c for c, row in zip(candidates, nvim_segment(candidates)) if len(row) == 1]
    print(f"{len(clusters)} clusters ({len(candidates) - len(clusters)} rejected by Neovim)")

    runs = shape_all(args.font, clusters, variations)
    glyphset = src.getGlyphSet(location=variations or None)
    order = src.getGlyphOrder()
    shaped, failed = {}, []
    for c, run in zip(clusters, runs):
        r = flatten(run, glyphset, order)
        if r:
            shaped[c] = r
        else:
            failed.append(c)
    if failed:
        print(f"{len(failed)} clusters could not be drawn by the source font (skipped)")

    m = target_metrics(args)
    glyphs = build_glyphs(shaped, src["head"].unitsPerEm, m, args.pad)
    cps = assign_codepoints(list(glyphs), existing)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.merge:
        font_path = out_dir / (Path(args.mono).stem + "-Bangla.ttf")
        family = write_merged(font_path, args, glyphs, cps, m)
    else:
        font_path, family = out_dir / "BanglaCells.ttf", "BanglaCells"
        write_standalone(font_path, glyphs, cps, m)
    write_map(cps, args, m)
    print(f"font: {font_path}  (family \"{family}\", {len(glyphs)} glyphs)")
    print(f"map:  {MAP_PATH}")

    if args.install:
        dest = Path.home() / "Library/Fonts" / font_path.name
        shutil.copy2(font_path, dest)
        print(f"installed: {dest}  (restart your terminal to load it)")


if __name__ == "__main__":
    main()
