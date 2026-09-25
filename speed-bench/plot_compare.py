#!/usr/bin/env python3
"""Compare several ds4-bench CSVs on one square chart.

Unlike plot_speed.py, which overlays prefill and generation on two y axes,
this stacks them as two panels over a shared x axis. Two scales that differ
by an order of magnitude do not belong on one plot, and a hidden right-hand
axis becomes actively misleading the moment the image is cropped or scaled.

Square output so `qlmanage -t` rasterises it without letterboxing or clipping.
Standard library only.
"""

import argparse
import csv
import math
from pathlib import Path

W = H = 1000
PAD_L, PAD_R, PAD_T, PAD_B = 96, 104, 150, 74
PANEL_GAP = 78

INK = "#14171c"
MUTED = "#79818f"
GRID = "#e6e9ee"
AXIS = "#aab2bd"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]  # slot 6 is violet, not the palette green: that green sits too close to the aqua in slot 3


def nice_ceil(v):
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 10):
        if v / mag <= step:
            return step * mag
    return 10 * mag


def read(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fp:
        for r in csv.DictReader(fp):
            steady = r.get("gen_steady_tps") or r.get("gen_tps")
            rows.append((int(r["ctx_tokens"]), float(r["prefill_tps"]), float(steady)))
    rows.sort()
    return rows


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def panel(out, series, labels, idx, y0, y1, x_max, title, unit):
    """Draw one panel; idx selects prefill (1) or generation (2) from the row."""
    peak = max(max(r[idx] for r in s) for s in series)
    y_max = nice_ceil(peak * 1.12)
    pw = W - PAD_L - PAD_R
    ph = y1 - y0

    sx = lambda v: PAD_L + (v / x_max) * pw
    sy = lambda v: y1 - (v / y_max) * ph

    out.append(f'<text x="{PAD_L}" y="{y0 - 16}" class="ptitle">{esc(title)}</text>')
    out.append(f'<text x="{W - PAD_R}" y="{y0 - 16}" class="punit" text-anchor="end">{esc(unit)}</text>')

    ticks = 4
    step = y_max / ticks
    for i in range(ticks + 1):
        v = step * i
        y = sy(v)
        out.append(f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L+pw}" y2="{y:.1f}"/>')
        lab = f"{v:.0f}" if y_max >= 20 else f"{v:.0f}"
        out.append(f'<text class="tick" x="{PAD_L-12}" y="{y+5:.1f}" text-anchor="end">{lab}</text>')

    out.append(f'<line class="axis" x1="{PAD_L}" y1="{y0}" x2="{PAD_L}" y2="{y1}"/>')
    out.append(f'<line class="axis" x1="{PAD_L}" y1="{y1}" x2="{PAD_L+pw}" y2="{y1}"/>')

    for x in sorted({r[0] for s in series for r in s}):
        out.append(f'<text class="tick" x="{sx(x):.1f}" y="{y1+26:.1f}" text-anchor="middle">{x//1024}k</text>')

    for n, rows in enumerate(series):
        pts = " ".join(f"{sx(r[0]):.1f},{sy(r[idx]):.1f}" for r in rows)
        out.append(f'<polyline class="line" stroke="{SERIES[n]}" points="{pts}"/>')
        for r in rows:
            out.append(f'<circle cx="{sx(r[0]):.1f}" cy="{sy(r[idx]):.1f}" r="5.5" fill="{SERIES[n]}" stroke="#ffffff" stroke-width="2.5"/>')

    # Label the last point of each series in the right margin, so identity never
    # rests on colour alone. Series whose final values are close would overprint
    # each other, so spread them apart vertically first.
    labels_at = sorted(
        ((sy(rows[-1][idx]), sx(rows[-1][0]), rows[-1][idx], SERIES[n])
         for n, rows in enumerate(series)),
        key=lambda t: t[0],
    )
    MIN_GAP = 19.0
    placed = []
    for y, x, value, colour in labels_at:
        if placed and y - placed[-1][0] < MIN_GAP:
            y = placed[-1][0] + MIN_GAP
        placed.append((y, x, value, colour))
    for y, x, value, colour in placed:
        out.append(
            f'<text class="val" x="{x+14:.1f}" y="{y+5:.1f}" fill="{colour}">{value:.1f}</text>'
        )


def main():
    ap = argparse.ArgumentParser(description="Compare ds4-bench CSVs on one square chart.")
    ap.add_argument("pairs", nargs="+", help="LABEL=path.csv")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--title", default="ds4-bench comparison")
    ap.add_argument("--subtitle", default="")
    args = ap.parse_args()

    labels, series = [], []
    for p in args.pairs:
        label, _, path = p.partition("=")
        if not path:
            raise SystemExit(f"expected LABEL=path.csv, got {p!r}")
        labels.append(label)
        series.append(read(path))

    x_max = max(r[0] for s in series for r in s) * 1.06

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        "<style>"
        f".grid{{stroke:{GRID};stroke-width:1}}"
        f".axis{{stroke:{AXIS};stroke-width:1.2}}"
        f".tick{{fill:{MUTED};font-size:15px;font-variant-numeric:tabular-nums}}"
        f".ptitle{{fill:{INK};font-size:19px;font-weight:650}}"
        f".punit{{fill:{MUTED};font-size:14px}}"
        f".val{{font-size:15px;font-weight:650;font-variant-numeric:tabular-nums}}"
        ".line{fill:none;stroke-width:2.6;stroke-linejoin:round;stroke-linecap:round}"
        f".title{{fill:{INK};font-size:27px;font-weight:700}}"
        f".sub{{fill:{MUTED};font-size:15px}}"
        f".leg{{fill:{INK};font-size:15px}}"
        "</style>",
        f'<text class="title" x="{PAD_L}" y="46">{esc(args.title)}</text>',
    ]
    if args.subtitle:
        out.append(f'<text class="sub" x="{PAD_L}" y="72">{esc(args.subtitle)}</text>')

    # Wrap the legend rather than letting entries run off the right edge.
    lx, ly, rows_used = PAD_L, 95, 1
    for n, lab in enumerate(labels):
        entry_w = 34 + len(lab) * 8 + 34
        if lx > PAD_L and lx + entry_w > W - PAD_R + 34:
            lx, ly, rows_used = PAD_L, ly + 26, rows_used + 1
        out.append(f'<rect x="{lx}" y="{ly}" width="26" height="4" rx="2" fill="{SERIES[n]}"/>')
        out.append(f'<text class="leg" x="{lx+34}" y="{ly+8}">{esc(lab)}</text>')
        lx += entry_w

    pad_t = PAD_T + (rows_used - 1) * 26
    avail = H - pad_t - PAD_B - PANEL_GAP
    ph = avail / 2
    panel(out, series, labels, 1, pad_t, pad_t + ph, x_max, "Prefill", "tokens / sec")
    top2 = pad_t + ph + PANEL_GAP
    panel(out, series, labels, 2, top2, top2 + ph, x_max, "Generation (steady)", "tokens / sec")

    out.append(f'<text class="sub" x="{W//2}" y="{H-22}" text-anchor="middle">context tokens</text>')
    out.append("</svg>")

    Path(args.output).write_text("\n".join(out), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
